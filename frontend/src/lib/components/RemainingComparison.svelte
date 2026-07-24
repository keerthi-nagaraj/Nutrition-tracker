<script lang="ts">
	import { mealFlow } from '$lib/stores/meal-flow.svelte';

	function confidenceLevel(score: number): 'low' | 'medium' | 'high' {
		if (score >= 0.8) return 'high';
		if (score >= 0.5) return 'medium';
		return 'low';
	}

	const totals = $derived(
		mealFlow.remainingFoods.reduce(
			(acc, f) => ({
				before: acc.before + f.before_weight_g,
				after: acc.after + f.after_weight_g,
				consumed: acc.consumed + f.consumed_weight_g
			}),
			{ before: 0, after: 0, consumed: 0 }
		)
	);
</script>

<section class="comparison">
	<div class="header">
		<h2>Before vs. after</h2>
	</div>

	{#if mealFlow.afterImagePreviewUrl}
		<div class="preview-pair">
			<figure>
				<img class="preview" src={mealFlow.imagePreviewUrl} alt="Meal before eating" />
				<figcaption>Before</figcaption>
			</figure>
			<figure>
				<img class="preview" src={mealFlow.afterImagePreviewUrl} alt="Meal after eating" />
				<figcaption>After</figcaption>
			</figure>
		</div>
	{/if}

	<div class="table-wrap">
		<table>
			<thead>
				<tr>
					<th>Food</th>
					<th>Before</th>
					<th>Remaining</th>
					<th>Consumed</th>
					<th>Confidence</th>
				</tr>
			</thead>
			<tbody>
				{#each mealFlow.remainingFoods as food (food.name)}
					<tr>
						<td>{food.name}</td>
						<td>{food.before_weight_g}g</td>
						<td>{food.after_weight_g}g</td>
						<td class="consumed">{food.consumed_weight_g}g</td>
						<td>
							<span class="confidence" data-level={confidenceLevel(food.confidence)}>
								{Math.round(food.confidence * 100)}%
							</span>
						</td>
					</tr>
				{/each}
			</tbody>
			<tfoot>
				<tr>
					<td>Total</td>
					<td>{totals.before}g</td>
					<td>{totals.after}g</td>
					<td class="consumed">{totals.consumed}g</td>
					<td></td>
				</tr>
			</tfoot>
		</table>
	</div>

	<div class="actions">
		<button type="button" class="secondary" onclick={() => mealFlow.reset()}>Start over</button>
		<button type="button" class="primary" onclick={() => mealFlow.calculateConsumedNutrition()}>
			Calculate nutrition
		</button>
	</div>
</section>

<style>
	.header {
		margin-bottom: var(--space-4);
	}

	h2 {
		font-size: 21px;
	}

	.preview-pair {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-3);
		max-width: 420px;
		margin: 0 auto var(--space-5);
	}

	.preview-pair figure {
		margin: 0;
		text-align: center;
	}

	.preview {
		width: 100%;
		border-radius: var(--radius-md);
		object-fit: cover;
		aspect-ratio: 3 / 4;
		box-shadow: var(--shadow-sm);
		border: 1px solid var(--color-border);
	}

	.preview-pair figcaption {
		margin-top: var(--space-1);
		font-size: 13px;
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

	tfoot td {
		border-top: 2px solid var(--color-border);
		font-weight: 700;
	}

	.consumed {
		color: var(--color-accent);
		font-weight: 700;
	}

	.confidence {
		font-size: 13px;
		font-weight: 600;
		padding: 2px var(--space-2);
		border-radius: 999px;
		background: var(--color-bg);
		color: var(--color-text-muted);
	}

	.confidence[data-level='low'] {
		color: var(--color-low);
	}
	.confidence[data-level='medium'] {
		color: var(--color-medium);
	}
	.confidence[data-level='high'] {
		color: var(--color-high);
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

	.primary:hover {
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
