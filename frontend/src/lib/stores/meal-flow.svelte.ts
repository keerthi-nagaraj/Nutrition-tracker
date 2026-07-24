import {
	analyzeMeal,
	analyzeMealRemaining,
	estimateMealNutrition,
	logMeal as logMealTool,
	resolveMealClarification
} from '$lib/mcp/tools';
import type {
	AnalyzedFood,
	ClarificationQuestion,
	EstimateNutritionResult,
	LogMealResult,
	MealType,
	RemainingFood,
	WeightRange
} from '$lib/mcp/types';

export type CaptureMode = 'single' | 'completion';

export type FlowStep =
	| 'idle'
	| 'analyzing'
	| 'clarify'
	| 'resolving'
	| 'confirm'
	| 'awaiting-after'
	| 'comparing'
	| 'remaining-result'
	| 'estimating'
	| 'result'
	| 'consumed-estimating'
	| 'consumed-result'
	| 'logging'
	| 'logged'
	| 'error';

export interface EditableFood {
	name: string;
	weight_g: number;
	weight_range_g?: WeightRange;
	/** 0-1 — portion_estimation confidence from analyze_meal's BEFORE-photo analysis. */
	confidence?: number;
}

const PATIENT_ID_KEY = 'nutrition-tracker-patient-id';

/** No auth in this app — a stable per-browser id is enough to satisfy the
 *  backend's patient_id field and let logged meals group together. */
function getOrCreatePatientId(): string {
	if (typeof localStorage === 'undefined') return 'local-patient';
	let id = localStorage.getItem(PATIENT_ID_KEY);
	if (!id) {
		id = crypto.randomUUID();
		localStorage.setItem(PATIENT_ID_KEY, id);
	}
	return id;
}

function fileToBase64(file: File): Promise<string> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => resolve(reader.result as string);
		reader.onerror = () => reject(reader.error ?? new Error('Could not read file.'));
		reader.readAsDataURL(file);
	});
}

function fromAnalyzed(f: AnalyzedFood): EditableFood {
	return {
		name: f.name,
		weight_g: f.estimated_weight_g,
		weight_range_g: f.weight_range_g,
		confidence: f.confidence?.portion_estimation
	};
}

/** Drives two flows against the MCP backend's tools:
 *
 *  single mode:     photo -> analyze -> (clarify) -> confirm/edit -> estimate -> log
 *  completion mode: BEFORE photo -> analyze -> (clarify) -> AFTER photo ->
 *                    compare (before/after/consumed per food) -> calories -> log
 *
 *  Both share Tool 1 (analyze_meal) + Tool 3 (resolve_meal_clarification) for
 *  the initial detection step — only what happens after differs. */
class MealFlow {
	step = $state<FlowStep>('idle');
	patientId = getOrCreatePatientId();
	mealType = $state<MealType>('unknown');
	mode = $state<CaptureMode>('single');
	timestamp = $state<string | null>(null);
	imagePreviewUrl = $state<string | null>(null);
	/** Only set in 'completion' mode, once the after photo is analyzed. */
	afterImagePreviewUrl = $state<string | null>(null);

	analysisId = $state<string | null>(null);
	questions = $state<ClarificationQuestion[]>([]);
	answers = $state<Record<string, string>>({});

	foods = $state<EditableFood[]>([]);
	estimate = $state<EstimateNutritionResult | null>(null);

	/** completion mode only: before/after/consumed per food from Tool 2b. */
	remainingFoods = $state<RemainingFood[]>([]);
	/** completion mode only: estimate_meal_nutrition's result, called on the
	 *  consumed weights — same shape as single-mode's `estimate`, just fed
	 *  different input and displayed by a different component. */
	consumedNutrition = $state<EstimateNutritionResult | null>(null);

	logResult = $state<LogMealResult | null>(null);
	errorMessage = $state<string | null>(null);

	/** Tool 1: analyze a photo. In 'single' mode this is the only photo; in
	 *  'completion' mode this is the BEFORE photo — success routes to
	 *  'awaiting-after' instead of 'confirm'. */
	async analyze(file: File) {
		this.#revokePreview();
		this.errorMessage = null;
		this.estimate = null;
		this.remainingFoods = [];
		this.consumedNutrition = null;
		this.logResult = null;
		this.imagePreviewUrl = URL.createObjectURL(file);
		this.timestamp = new Date().toISOString();
		this.step = 'analyzing';

		try {
			const base64 = await fileToBase64(file);
			let result = await analyzeMeal(this.patientId, this.mealType, this.timestamp, base64);
			this.analysisId = result.analysis_id;

			/** The user can reject analyze_meal's "does this look correct?"
			 *  elicitation and type a free-text fix (see ElicitationDialog) —
			 *  the backend saves that as session-state feedback and re-runs
			 *  Gemini with it only on the NEXT analyze_meal call with the same
			 *  args (server.py's analyze_meal docstring), so the correction
			 *  doesn't take effect until we call it again ourselves. Capped
			 *  client-side too: once the backend's own round limit is hit it
			 *  keeps returning confirmed:false with the same feedback forever
			 *  rather than signalling that the limit was reached. */
			for (
				let round = 0;
				result.user_confirmation?.asked &&
				result.user_confirmation.confirmed === false &&
				result.user_confirmation.feedback &&
				round < 3;
				round++
			) {
				result = await analyzeMeal(this.patientId, this.mealType, this.timestamp, base64);
				this.analysisId = result.analysis_id;
			}

			const { foods, needs_confirmation } = result;

			if (needs_confirmation.required && needs_confirmation.questions.length) {
				this.questions = needs_confirmation.questions;
				this.answers = Object.fromEntries(
					needs_confirmation.questions.map((q) => [q.question_id, q.options[0] ?? ''])
				);
				this.step = 'clarify';
				return;
			}

			if (!foods.length) {
				this.step = 'error';
				this.errorMessage = 'No food items were detected in that photo — try another one.';
				return;
			}

			this.foods = foods.map(fromAnalyzed);
			this.step = this.mode === 'completion' ? 'awaiting-after' : 'confirm';
		} catch (err) {
			this.step = 'error';
			this.errorMessage = err instanceof Error ? err.message : String(err);
		}
	}

	setAnswer(questionId: string, answer: string) {
		this.answers = { ...this.answers, [questionId]: answer };
	}

	async submitClarification() {
		if (!this.analysisId) return;
		this.step = 'resolving';
		this.errorMessage = null;

		try {
			const answers = this.questions.map((q) => ({
				question_id: q.question_id,
				answer: this.answers[q.question_id] ?? ''
			}));
			const { foods } = await resolveMealClarification(this.analysisId, answers);
			if (!foods.length) {
				this.step = 'error';
				this.errorMessage = 'No food items left after clarification — try another photo.';
				return;
			}
			this.foods = foods.map((f) => ({ name: f.name, weight_g: f.estimated_weight_g }));
			this.step = this.mode === 'completion' ? 'awaiting-after' : 'confirm';
		} catch (err) {
			this.step = 'error';
			this.errorMessage = err instanceof Error ? err.message : String(err);
		}
	}

	updateFood(index: number, patch: Partial<EditableFood>) {
		this.foods = this.foods.map((f, i) => (i === index ? { ...f, ...patch } : f));
	}

	removeFood(index: number) {
		this.foods = this.foods.filter((_, i) => i !== index);
	}

	addFood() {
		this.foods = [...this.foods, { name: '', weight_g: 100 }];
	}

	backToConfirm() {
		this.errorMessage = null;
		this.step = 'confirm';
	}

	backToAwaitingAfter() {
		this.errorMessage = null;
		this.step = 'awaiting-after';
	}

	/** single mode only, Tool 4: confirmed foods -> full nutrition breakdown. */
	async confirm() {
		if (!this.foods.length) return;
		this.step = 'estimating';
		this.errorMessage = null;

		try {
			this.estimate = await estimateMealNutrition(
				this.foods.map((f) => ({ name: f.name, weight_g: f.weight_g }))
			);
			this.step = 'result';
		} catch (err) {
			this.step = 'error';
			this.errorMessage = err instanceof Error ? err.message : String(err);
		}
	}

	/** completion mode only, Tool 2b: the AFTER photo + the analysis_id from
	 *  the BEFORE photo's analyze() call -> before/after/consumed per food. */
	async analyzeAfter(file: File) {
		if (!this.analysisId) return;
		if (this.afterImagePreviewUrl) URL.revokeObjectURL(this.afterImagePreviewUrl);
		this.afterImagePreviewUrl = URL.createObjectURL(file);
		this.errorMessage = null;
		this.step = 'comparing';

		try {
			const base64 = await fileToBase64(file);
			const { foods } = await analyzeMealRemaining(this.analysisId, base64);
			if (!foods.length) {
				this.step = 'error';
				this.errorMessage = 'No matching foods could be compared — try another after photo.';
				return;
			}
			this.remainingFoods = foods;
			this.step = 'remaining-result';
		} catch (err) {
			this.step = 'error';
			this.errorMessage = err instanceof Error ? err.message : String(err);
		}
	}

	/** completion mode only, Tool 4: consumed weights -> nutrition (same
	 *  estimate_meal_nutrition call single mode's confirm() makes). */
	async calculateConsumedNutrition() {
		if (!this.remainingFoods.length) return;
		this.step = 'consumed-estimating';
		this.errorMessage = null;

		try {
			this.consumedNutrition = await estimateMealNutrition(
				this.remainingFoods.map((f) => ({ name: f.name, weight_g: f.consumed_weight_g }))
			);
			this.step = 'consumed-result';
		} catch (err) {
			this.step = 'error';
			this.errorMessage = err instanceof Error ? err.message : String(err);
		}
	}

	async logMeal() {
		if (!this.timestamp) return;
		const result = this.mode === 'completion' ? this.consumedNutrition : this.estimate;
		if (!result) return;
		this.step = 'logging';
		this.errorMessage = null;

		try {
			const foodsWithMatch = result.foods.map((f) => ({
				name: f.name,
				calories: f.calories,
				fdc_id: f.fdc_id,
				match_confidence: f.match_confidence,
				source: f.source,
				source_id: f.source_id,
				sources: f.sources
			}));
			this.logResult = await logMealTool(
				this.patientId,
				this.timestamp,
				this.mealType,
				foodsWithMatch,
				result.nutrition
			);
			this.step = 'logged';
		} catch (err) {
			this.step = 'error';
			this.errorMessage = err instanceof Error ? err.message : String(err);
		}
	}

	reset() {
		this.#revokePreview();
		this.step = 'idle';
		this.mode = 'single';
		this.mealType = 'unknown';
		this.timestamp = null;
		this.analysisId = null;
		this.questions = [];
		this.answers = {};
		this.foods = [];
		this.estimate = null;
		this.remainingFoods = [];
		this.consumedNutrition = null;
		this.logResult = null;
		this.errorMessage = null;
	}

	#revokePreview() {
		if (this.imagePreviewUrl) URL.revokeObjectURL(this.imagePreviewUrl);
		this.imagePreviewUrl = null;
		if (this.afterImagePreviewUrl) URL.revokeObjectURL(this.afterImagePreviewUrl);
		this.afterImagePreviewUrl = null;
	}
}

export const mealFlow = new MealFlow();
