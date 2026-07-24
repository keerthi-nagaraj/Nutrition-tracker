<script lang="ts">
	import { mealFlow } from '$lib/stores/meal-flow.svelte';

	let dragging = $state(false);
	let fileInput: HTMLInputElement;

	function handleFiles(files: FileList | null) {
		const file = files?.[0];
		if (file) mealFlow.analyzeAfter(file);
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragging = false;
		handleFiles(e.dataTransfer?.files ?? null);
	}
</script>

<section class="awaiting">
	<div class="layout">
		{#if mealFlow.imagePreviewUrl}
			<img class="preview" src={mealFlow.imagePreviewUrl} alt="Meal before eating" />
		{/if}

		<div class="items">
			<h2>Before you eat</h2>
			<p class="subtitle">Fix anything wrong now — this is the baseline the after photo gets compared against.</p>

			<ul>
				{#each mealFlow.foods as food, i (i)}
					<li class="item">
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
						</div>
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
		</div>
	</div>

	<div
		class="dropzone"
		class:dragging
		role="button"
		tabindex="0"
		onclick={() => fileInput.click()}
		onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInput.click()}
		ondragover={(e) => {
			e.preventDefault();
			dragging = true;
		}}
		ondragleave={() => (dragging = false)}
		ondrop={onDrop}
	>
		<input
			bind:this={fileInput}
			type="file"
			accept="image/*"
			hidden
			onchange={(e) => handleFiles((e.target as HTMLInputElement).files)}
		/>
		<div class="icon" aria-hidden="true">🍽️</div>
		<p class="title">Now drop the AFTER-eating photo here, or click to choose one</p>
		<p class="hint">We'll compare it against what's listed above</p>
	</div>

	<div class="actions">
		<button type="button" class="secondary" onclick={() => mealFlow.reset()}>Start over</button>
	</div>
</section>

<style>
	.layout {
		display: grid;
		grid-template-columns: 220px 1fr;
		gap: var(--space-5);
		align-items: center;
		margin-bottom: var(--space-5);
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
		grid-template-columns: 1fr auto auto;
		gap: var(--space-2);
		align-items: center;
		padding: var(--space-2);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
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

	.grams input {
		width: 68px;
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

	.dropzone {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		padding: var(--space-6) var(--space-5);
		border: 1.5px dashed var(--color-accent);
		border-radius: var(--radius-lg);
		background: var(--color-accent-soft);
		text-align: center;
		transition: background 0.15s ease;
	}

	.dropzone:hover,
	.dropzone:focus-visible,
	.dropzone.dragging {
		background: var(--color-secondary-soft);
		outline: none;
	}

	.icon {
		font-size: 28px;
	}

	.title {
		margin: 0;
		font-size: 16px;
		font-weight: 600;
	}

	.hint {
		margin: 0;
		color: var(--color-text-muted);
		font-size: 14px;
	}

	.actions {
		display: flex;
		justify-content: flex-end;
		margin-top: var(--space-4);
	}

	.secondary {
		border-radius: var(--radius-sm);
		padding: var(--space-2) var(--space-4);
		font-weight: 600;
		font-size: 15px;
		border: 1px solid var(--color-border);
		background: none;
		color: var(--color-text);
	}

	.secondary:hover {
		background: var(--color-surface);
	}
</style>
