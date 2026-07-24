<script lang="ts">
	import { mealFlow } from '$lib/stores/meal-flow.svelte';
	import type { ProviderName } from '$lib/mcp/types';

	const result = $derived(mealFlow.consumedNutrition!);

	const PROVIDER_LABELS: Record<ProviderName, string> = {
		usda: 'USDA FDC',
		openfoodfacts: 'Open Food Facts',
		nutritionix: 'Nutritionix',
		indb: 'INDB'
	};

	function providerLabel(source: ProviderName | null): string {
		return source ? PROVIDER_LABELS[source] : 'Unknown';
	}

	const tiles = $derived([
		{ label: 'Calories', value: Math.round(result.nutrition.calories), unit: 'kcal', nutrient: 'calories' },
		{ label: 'Protein', value: Math.round(result.nutrition.protein_g), unit: 'g', nutrient: 'protein' },
		{ label: 'Carbs', value: Math.round(result.nutrition.carbohydrate_g), unit: 'g', nutrient: 'carbs' },
		{ label: 'Fat', value: Math.round(result.nutrition.fat_g), unit: 'g', nutrient: 'fat' },
		{ label: 'Fiber', value: Math.round(result.nutrition.fiber_g), unit: 'g', nutrient: null },
		{ label: 'Sodium', value: Math.round(result.nutrition.sodium_mg), unit: 'mg', nutrient: null }
	]);
</script>

<section class="summary">
	<div class="header">
		<h2>Nutrition consumed</h2>
		{#if mealFlow.timestamp}
			<span class="timestamp">{new Date(mealFlow.timestamp).toLocaleString()}</span>
		{/if}
	</div>

	<div class="tiles">
		{#each tiles as tile (tile.label)}
			<div class="tile" data-nutrient={tile.nutrient}>
				<span class="tile-value">{tile.value}<small>{tile.unit}</small></span>
				<span class="tile-label">{tile.label}</span>
			</div>
		{/each}
	</div>

	<div class="table-wrap">
		<table>
			<thead>
				<tr>
					<th>Food</th>
					<th>Calories</th>
					<th>Reference matched</th>
				</tr>
			</thead>
			<tbody>
				{#each result.foods as food (food.name)}
					<tr class:unmatched={food.source == null}>
						<td>{food.name}</td>
						<td>{Math.round(food.calories)} kcal</td>
						<td>
							{#if food.source != null}
								<span class="provider" title={food.matched_description ?? undefined}>
									{providerLabel(food.source)}
								</span>
								<span class="ref-id">#{food.source_id ?? '—'}</span>
								<span class="match-pct">{Math.round(food.match_confidence * 100)}% match</span>
							{:else}
								No match
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if mealFlow.step === 'logged' && mealFlow.logResult}
		<p class="logged-banner">✓ Logged — meal ID {mealFlow.logResult.meal_id}</p>
	{/if}

	<div class="actions">
		{#if mealFlow.step === 'logged'}
			<button type="button" class="primary" onclick={() => mealFlow.reset()}>
				Track another meal
			</button>
		{:else}
			<button type="button" class="secondary" onclick={() => mealFlow.reset()}>
				Start over
			</button>
			<button
				type="button"
				class="primary"
				disabled={mealFlow.step === 'logging'}
				onclick={() => mealFlow.logMeal()}
			>
				{mealFlow.step === 'logging' ? 'Logging…' : 'Log this meal'}
			</button>
		{/if}
	</div>
</section>

<style>
	.header {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		margin-bottom: var(--space-4);
	}

	h2 {
		font-size: 21px;
	}

	.timestamp {
		font-size: 14px;
		color: var(--color-text-muted);
	}

	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
		gap: var(--space-2);
		margin-bottom: var(--space-4);
	}

	.tile {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: var(--space-3);
		border-radius: var(--radius-md);
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-left: 4px solid var(--color-border);
	}

	.tile[data-nutrient='calories'] {
		border-left-color: var(--color-calories);
	}
	.tile[data-nutrient='protein'] {
		border-left-color: var(--color-protein);
	}
	.tile[data-nutrient='carbs'] {
		border-left-color: var(--color-carbs);
	}
	.tile[data-nutrient='fat'] {
		border-left-color: var(--color-fat);
	}

	.tile-value {
		font-size: 24px;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}

	.tile-value small {
		font-size: 13px;
		font-weight: 500;
		color: var(--color-text-muted);
		margin-left: 2px;
	}

	.tile-label {
		font-size: 14px;
		color: var(--color-text-muted);
	}

	.table-wrap {
		overflow-x: auto;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 15px;
	}

	th,
	td {
		text-align: left;
		padding: var(--space-2) var(--space-3);
		white-space: nowrap;
	}

	thead th {
		color: var(--color-text-muted);
		font-weight: 600;
		border-bottom: 1px solid var(--color-border);
	}

	tbody tr:not(:last-child) td {
		border-bottom: 1px solid var(--color-border);
	}

	tr.unmatched {
		color: var(--color-text-muted);
		font-style: italic;
	}

	.provider {
		font-weight: 600;
	}

	.ref-id {
		color: var(--color-text-muted);
		margin-left: var(--space-1);
		font-family: var(--font-mono);
		font-size: 13px;
	}

	.match-pct {
		display: block;
		color: var(--color-text-muted);
		font-size: 12px;
		margin-top: 2px;
	}

	.logged-banner {
		background: var(--color-accent-soft);
		color: var(--color-success);
		border-radius: var(--radius-sm);
		padding: var(--space-2) var(--space-3);
		font-size: 15px;
		font-weight: 600;
		margin: var(--space-3) 0 0;
	}

	.actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-2);
		margin-top: var(--space-5);
	}

	.primary,
	.secondary {
		border-radius: var(--radius-sm);
		padding: var(--space-2) var(--space-4);
		font-weight: 600;
		font-size: 16px;
		border: 1px solid transparent;
	}

	.primary {
		background: var(--color-accent);
		color: var(--color-accent-contrast);
	}

	.primary:disabled {
		opacity: 0.5;
	}

	.primary:not(:disabled):hover {
		filter: brightness(1.05);
	}

	.secondary {
		background: none;
		border-color: var(--color-border);
		color: var(--color-text);
	}

	.secondary:hover {
		background: var(--color-surface);
	}
</style>
