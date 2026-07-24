<script lang="ts">
	import { mealFlow, type CaptureMode } from '$lib/stores/meal-flow.svelte';
	import type { MealType } from '$lib/mcp/types';

	const mealTypes: MealType[] = ['breakfast', 'lunch', 'dinner', 'snack', 'unknown'];
	const modes: { value: CaptureMode; label: string }[] = [
		{ value: 'single', label: 'Single photo' },
		{ value: 'completion', label: 'Before & after' }
	];

	let dragging = $state(false);
	let fileInput: HTMLInputElement;

	function handleFiles(files: FileList | null) {
		const file = files?.[0];
		if (file) mealFlow.analyze(file);
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragging = false;
		handleFiles(e.dataTransfer?.files ?? null);
	}
</script>

<div class="controls">
	<div class="tabs" role="tablist">
		{#each modes as m (m.value)}
			<button
				type="button"
				role="tab"
				aria-selected={mealFlow.mode === m.value}
				class:active={mealFlow.mode === m.value}
				onclick={() => (mealFlow.mode = m.value)}
			>
				{m.label}
			</button>
		{/each}
	</div>

	<div class="meal-type">
		<label for="meal-type-select">Meal type</label>
		<select id="meal-type-select" bind:value={mealFlow.mealType}>
			{#each mealTypes as type (type)}
				<option value={type}>{type}</option>
			{/each}
		</select>
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

	<div class="icon" aria-hidden="true">📷</div>
	{#if mealFlow.mode === 'completion'}
		<p class="title">Drop the BEFORE-eating photo here, or click to choose one</p>
		<p class="hint">You'll be asked for the after photo once this one's analyzed</p>
	{:else}
		<p class="title">Drop a meal photo here, or click to choose one</p>
		<p class="hint">JPG, PNG, HEIC — detects items and estimated grams</p>
	{/if}
</div>

<style>
	.controls {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
	}

	.tabs {
		display: inline-flex;
		border: 1px solid var(--color-border);
		border-radius: 999px;
		padding: 2px;
		background: var(--color-surface);
	}

	.tabs button {
		border: none;
		background: none;
		color: var(--color-text-muted);
		padding: var(--space-1) var(--space-3);
		border-radius: 999px;
		font-size: 14px;
		font-weight: 600;
	}

	.tabs button.active {
		background: var(--color-accent);
		color: var(--color-accent-contrast);
	}

	.meal-type {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.meal-type label {
		font-size: 15px;
		color: var(--color-text-muted);
	}

	.meal-type select {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text);
		padding: var(--space-1) var(--space-2);
		text-transform: capitalize;
	}

	.dropzone {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		padding: var(--space-8) var(--space-5);
		border: 1.5px dashed var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
		text-align: center;
		transition:
			border-color 0.15s ease,
			background 0.15s ease;
	}

	.dropzone:hover,
	.dropzone:focus-visible {
		border-color: var(--color-accent);
		background: var(--color-accent-soft);
		outline: none;
	}

	.dropzone.dragging {
		border-color: var(--color-accent);
		background: var(--color-accent-soft);
	}

	.icon {
		font-size: 32px;
	}

	.title {
		margin: 0;
		font-size: 17px;
		font-weight: 600;
	}

	.hint {
		margin: 0;
		color: var(--color-text-muted);
		font-size: 15px;
	}
</style>
