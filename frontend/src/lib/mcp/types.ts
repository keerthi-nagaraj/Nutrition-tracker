export type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack' | 'unknown';

export interface WeightRange {
	min: number | null;
	max: number | null;
}

export interface FoodConfidence {
	food_identification: number;
	portion_estimation: number;
}

/** Shape of one entry in analyze_meal's `foods`. When the backend resolves a
 *  clarification question internally (real MCP elicitation, or
 *  resolve_meal_clarification), it returns the trimmed {name,
 *  estimated_weight_g} shape instead of the full detection shape — so
 *  everything but name/estimated_weight_g may be absent. */
export interface AnalyzedFood {
	name: string;
	fdc_search_hint?: string;
	estimated_weight_g: number;
	weight_range_g?: WeightRange;
	confidence?: FoodConfidence;
}

export interface ClarificationQuestion {
	question_id: string;
	food_id: string;
	type: 'single_select';
	question: string;
	options: string[];
}

export interface NeedsConfirmation {
	required: boolean;
	questions: ClarificationQuestion[];
}

export interface UserConfirmation {
	asked: boolean;
	confirmed?: boolean;
	feedback?: string;
}

export interface AnalyzeMealResult {
	analysis_id: string;
	foods: AnalyzedFood[];
	needs_confirmation: NeedsConfirmation;
	user_confirmation?: UserConfirmation;
}

export interface CompletionFood {
	name: string;
	consumed_weight_g: number;
	confidence: number;
}

export interface AnalyzeMealCompletionResult {
	foods: CompletionFood[];
	needs_confirmation: NeedsConfirmation;
}

export interface RemainingFood {
	name: string;
	before_weight_g: number;
	after_weight_g: number;
	consumed_weight_g: number;
	confidence: number;
}

export interface AnalyzeMealRemainingResult {
	foods: RemainingFood[];
}

export interface ClarificationAnswer {
	question_id: string;
	answer: string;
}

export interface ResolvedFood {
	name: string;
	estimated_weight_g: number;
}

export interface ResolveClarificationResult {
	foods: ResolvedFood[];
}

export interface NutritionInputFood {
	name: string;
	weight_g: number;
}

export interface NutritionTotals {
	calories: number;
	protein_g: number;
	carbohydrate_g: number;
	fat_g: number;
	fiber_g: number;
	sugar_g: number;
	sodium_mg: number;
	potassium_mg: number;
}

export type ProviderName = 'usda' | 'openfoodfacts' | 'nutritionix' | 'indb';

export interface MatchedFood {
	name: string;
	calories: number;
	fdc_id: string | number | null;
	match_confidence: number;
	matched_description: string | null;
	source: ProviderName | null;
	source_id: string | number | null;
	sources: ProviderName[];
}

export interface EstimateNutritionResult {
	foods: MatchedFood[];
	nutrition: NutritionTotals;
}

export interface LogMealResult {
	meal_id: string;
	status: string;
}

export interface ToolError {
	error: true;
	message: string;
	hint?: string;
}
