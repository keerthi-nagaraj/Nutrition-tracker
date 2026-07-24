import { mcp } from './client.svelte';
import type {
	AnalyzeMealCompletionResult,
	AnalyzeMealRemainingResult,
	AnalyzeMealResult,
	ClarificationAnswer,
	EstimateNutritionResult,
	LogMealResult,
	MealType,
	NutritionInputFood,
	NutritionTotals,
	ResolveClarificationResult,
	ToolError
} from './types';

function unwrap<T>(result: T | ToolError): T {
	if (result && typeof result === 'object' && 'error' in result && result.error) {
		throw new Error((result as ToolError).message);
	}
	return result as T;
}

/** Tool 1: photo -> detected foods + optional clarification questions. */
export async function analyzeMeal(
	patientId: string,
	mealType: MealType,
	timestamp: string,
	image: string
): Promise<AnalyzeMealResult> {
	const result = await mcp.callTool<AnalyzeMealResult | ToolError>('analyze_meal', {
		patient_id: patientId,
		meal_type: mealType,
		timestamp,
		image
	});
	return unwrap(result);
}

/** Tool 2: before/after photos -> consumed weight per food. */
export async function analyzeMealCompletion(
	patientId: string,
	mealType: MealType,
	beforeImage: string,
	afterImage: string
): Promise<AnalyzeMealCompletionResult> {
	const result = await mcp.callTool<AnalyzeMealCompletionResult | ToolError>(
		'analyze_meal_completion',
		{ patient_id: patientId, meal_type: mealType, before_image: beforeImage, after_image: afterImage }
	);
	return unwrap(result);
}

/** Tool 2b: step two of the two-step before/after flow — the analysis_id from
 *  analyzeMeal's BEFORE photo, plus the AFTER photo -> before/after/consumed
 *  weight per food (consumed computed by the backend, not guessed by Gemini). */
export async function analyzeMealRemaining(
	analysisId: string,
	afterImage: string
): Promise<AnalyzeMealRemainingResult> {
	const result = await mcp.callTool<AnalyzeMealRemainingResult | ToolError>('analyze_meal_remaining', {
		analysis_id: analysisId,
		after_image: afterImage
	});
	return unwrap(result);
}

/** Tool 3: apply clarification answers to a prior analyze_meal call, no re-run of Gemini. */
export async function resolveMealClarification(
	analysisId: string,
	answers: ClarificationAnswer[]
): Promise<ResolveClarificationResult> {
	const result = await mcp.callTool<ResolveClarificationResult | ToolError>(
		'resolve_meal_clarification',
		{ analysis_id: analysisId, answers }
	);
	return unwrap(result);
}

/** Tool 4: confirmed foods -> FDC-matched nutrition (calories per food, full
 *  macro totals). Used by both the single-photo flow and the before/after
 *  flow's consumed-weight output — a caller that only wants calories/
 *  protein/carbs/fat/fiber/sodium just ignores sugar_g/potassium_mg in the
 *  totals rather than calling a separate tool. */
export async function estimateMealNutrition(
	foods: NutritionInputFood[]
): Promise<EstimateNutritionResult> {
	const result = await mcp.callTool<EstimateNutritionResult | ToolError>('estimate_meal_nutrition', {
		foods
	});
	return unwrap(result);
}

/** Tool 5: persist the meal, return a meal_id. */
export async function logMeal(
	patientId: string,
	timestamp: string,
	mealType: MealType,
	foods: unknown[],
	nutrition: NutritionTotals
): Promise<LogMealResult> {
	const result = await mcp.callTool<LogMealResult | ToolError>('log_meal', {
		patient_id: patientId,
		timestamp,
		meal_type: mealType,
		foods,
		nutrition
	});
	return unwrap(result);
}
