<script lang="ts">
	import { mealFlow } from '$lib/stores/meal-flow.svelte';

	function confidenceLevel(score: number): 'low' | 'medium' | 'high' {
		if (score >= 0.8) return 'high';
		if (score >= 0.5) return 'medium';
		return 'low';
	}
</script>

<section class="editor">
	<div class="layout">
		{#if mealFlow.imagePreviewUrl}
			<img class="preview" src={mealFlow.imagePreviewUrl} alt="Uploaded meal" />
		{/if}

		<div class="items">
			<h2>Detected items</h2>
			<p class="subtitle">Review or edit before estimating nutrition — nothing is logged yet.</p>

			<ul>
				{#each mealFlow.foods as food, i (i)}
					{@const portionConfidence = food.confidence}
					<li class="item" data-confidence={portionConfidence != null ? confidenceLevel(portionConfidence) : undefined}>
						<input
							class="name"
							type="text"
							value={food.name}
							placeholder="Food name"
							oninput={(e) => mealFlow.updateFood(i, { name: (e.target as HTMLInputElement).value })}
						/>
						<div class="grams">
							<input
								type="number"
								min="0"
								step="1"
								value={food.weight_g}
								oninput={(e) =>
									mealFlow.updateFood(i, { weight_g: Number((e.target as HTMLInputElement).value) })}
							/>
							<span>g</span>
							{#if food.weight_range_g?.min != null && food.weight_range_g?.max != null}
								<span class="range" title="Plausible weight range from the photo"
									>({food.weight_range_g.min}–{food.weight_range_g.max}g)</span
								>
							{/if}
						</div>
						{#if portionConfidence != null}
							<span
								class="confidence"
								data-level={confidenceLevel(portionConfidence)}
								title="Portion-estimation confidence"
							>
								{Math.round(portionConfidence * 100)}%
							</span>
						{/if}
						<button
							type="button"
							class="remove"
							aria-label={`Remove ${food.name || 'item'}`}
							onclick={() => mealFlow.removeFood(i)}
						>
							✕
						</button>
					</li>
				{/each}
			</ul>

			<button type="button" class="add" onclick={() => mealFlow.addFood()}> + Add item </button>

			<div class="actions">
				<button type="button" class="secondary" onclick={() => mealFlow.reset()}>
					Start over
				</button>
				<button
					type="button"
					class="primary"
					disabled={!mealFlow.foods.length}
					onclick={() => mealFlow.confirm()}
				>
					Confirm &amp; estimate nutrition
				</button>
			</div>
		</div>
	</div>
</section>

<style>
	.layout {
		display: grid;
		grid-template-columns: 220px 1fr;
		gap: var(--space-5);
		align-items: center;
	}

	@media (max-width: 640px) {
		.layout {
			grid-template-columns: 1fr;
		}
	}

	.preview {
		width: 100%;
		border-radius: var(--radius-md);
		object-fit: cover;
		aspect-ratio: 3 / 4;
		box-shadow: var(--shadow-sm);
		border: 1px solid var(--color-border);
	}

	h2 {
		font-size: 21px;
	}

	.subtitle {
		margin: var(--space-1) 0 var(--space-4);
		color: var(--color-text-muted);
		font-size: 15px;
	}

	ul {
		list-style: none;
		margin: 0 0 var(--space-3);
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.item {
		display: grid;
		grid-template-columns: 1fr auto auto auto;
		gap: var(--space-2);
		align-items: center;
		padding: var(--space-2);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		border-left: 3px solid var(--color-text-muted);
	}

	.item[data-confidence='low'] {
		border-left-color: var(--color-low);
	}
	.item[data-confidence='medium'] {
		border-left-color: var(--color-medium);
	}
	.item[data-confidence='high'] {
		border-left-color: var(--color-high);
	}

	input {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-bg);
		color: var(--color-text);
		padding: var(--space-2);
	}

	.name {
		min-width: 0;
	}

	.grams {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		color: var(--color-text-muted);
		font-size: 15px;
		white-space: nowrap;
	}

	.grams .range {
		font-size: 12px;
		color: var(--color-text-muted);
		opacity: 0.8;
	}

	.grams input {
		width: 68px;
	}

	.confidence {
		font-size: 13px;
		font-weight: 600;
		padding: 2px var(--space-2);
		border-radius: 999px;
		white-space: nowrap;
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

	.remove {
		border: none;
		background: none;
		color: var(--color-text-muted);
		font-size: 16px;
		padding: var(--space-1);
		border-radius: var(--radius-sm);
	}

	.remove:hover {
		color: var(--color-danger);
		background: var(--color-danger-soft);
	}

	.add {
		border: 1px dashed var(--color-border);
		background: none;
		color: var(--color-text-muted);
		border-radius: var(--radius-sm);
		padding: var(--space-2);
		width: 100%;
		font-size: 15px;
	}

	.add:hover {
		border-color: var(--color-accent);
		color: var(--color-accent);
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
