<script lang="ts">
	import ImageDropzone from '$lib/components/ImageDropzone.svelte';
	import ClarificationQuestions from '$lib/components/ClarificationQuestions.svelte';
	import DetectedItemsEditor from '$lib/components/DetectedItemsEditor.svelte';
	import AwaitingAfterPhoto from '$lib/components/AwaitingAfterPhoto.svelte';
	import RemainingComparison from '$lib/components/RemainingComparison.svelte';
	import ConsumedNutritionSummary from '$lib/components/ConsumedNutritionSummary.svelte';
	import NutritionSummary from '$lib/components/NutritionSummary.svelte';
	import { mcp } from '$lib/mcp/client.svelte';
	import { mealFlow } from '$lib/stores/meal-flow.svelte';

	const connectionLabels = {
		idle: 'Not connected',
		connecting: 'Connecting…',
		connected: 'Connected',
		error: 'Connection failed'
	} as const;

	const loadingLabels = {
		analyzing: 'Detecting food items in your photo…',
		resolving: 'Applying your answers…',
		comparing: 'Comparing before and after photos…',
		estimating: 'Looking up nutrition data…',
		'consumed-estimating': 'Calculating nutrition consumed…',
		logging: 'Logging meal…'
	} as const;
</script>

<svelte:head>
	<title>Nutrition Tracker</title>
</svelte:head>

<header>
	<h1>Nutrition Tracker</h1>
	<div class="connection" data-status={mcp.status} title={mcp.errorMessage ?? undefined}>
		<span class="dot"></span>
		<span>{connectionLabels[mcp.status]}</span>
		{#if mcp.status === 'error'}
			<button type="button" onclick={() => mcp.reconnect()}>Retry</button>
		{/if}
	</div>
</header>

<main>
	{#if mealFlow.step === 'idle'}
		<ImageDropzone />
	{:else if mealFlow.step === 'analyzing' || mealFlow.step === 'resolving' || mealFlow.step === 'comparing' || mealFlow.step === 'estimating' || mealFlow.step === 'consumed-estimating' || mealFlow.step === 'logging'}
		<div class="loading">
			<span class="spinner" aria-hidden="true"></span>
			<p>{loadingLabels[mealFlow.step]}</p>
		</div>
	{:else if mealFlow.step === 'clarify'}
		<ClarificationQuestions />
	{:else if mealFlow.step === 'confirm'}
		<DetectedItemsEditor />
	{:else if mealFlow.step === 'awaiting-after'}
		<AwaitingAfterPhoto />
	{:else if mealFlow.step === 'remaining-result'}
		<RemainingComparison />
	{:else if (mealFlow.step === 'result' || (mealFlow.step === 'logged' && mealFlow.mode === 'single')) && mealFlow.estimate}
		<NutritionSummary />
	{:else if (mealFlow.step === 'consumed-result' || (mealFlow.step === 'logged' && mealFlow.mode === 'completion')) && mealFlow.consumedNutrition}
		<ConsumedNutritionSummary />
	{:else if mealFlow.step === 'error'}
		<div class="error">
			<p>{mealFlow.errorMessage ?? 'Something went wrong.'}</p>
			<div class="actions">
				<button type="button" class="secondary" onclick={() => mealFlow.reset()}>Back</button>
				{#if mealFlow.mode === 'completion' && mealFlow.remainingFoods.length}
					<button type="button" class="primary" onclick={() => mealFlow.calculateConsumedNutrition()}>
						Try again
					</button>
				{:else if mealFlow.mode === 'completion' && mealFlow.foods.length}
					<button type="button" class="primary" onclick={() => mealFlow.backToAwaitingAfter()}>
						Try the after photo again
					</button>
				{:else if mealFlow.mode === 'single' && mealFlow.foods.length}
					<button type="button" class="primary" onclick={() => mealFlow.confirm()}>
						Try again
					</button>
				{/if}
			</div>
		</div>
	{/if}
</main>

<style>
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: var(--space-6);
	}

	h1 {
		font-size: 35px;
		color: rgb(207, 82, 36);
	}

	/* Connection badge */
	.connection {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-1) var(--space-3);
		border-radius: 999px;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		font-size: 15px;
		color: var(--color-text-muted);
	}

	.connection .dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--color-text-muted);
		flex-shrink: 0;
	}

	.connection[data-status='connected'] .dot {
		background: var(--color-success);
	}

	.connection[data-status='connecting'] .dot {
		background: var(--color-medium);
		animation: pulse 1.2s ease-in-out infinite;
	}

	.connection[data-status='error'] .dot {
		background: var(--color-danger);
	}

	.connection button {
		border: none;
		background: none;
		color: var(--color-accent);
		font-size: 15px;
		font-weight: 600;
		padding: 0;
		margin-left: var(--space-1);
	}

	.connection button:hover {
		text-decoration: underline;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.35;
		}
	}

	/* Loading state */
	.loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-8) var(--space-5);
		color: var(--color-text-muted);
	}

	.spinner {
		width: 28px;
		height: 28px;
		border-radius: 50%;
		border: 3px solid var(--color-border);
		border-top-color: var(--color-accent);
		animation: spin 0.8s linear infinite;
	}

	.loading p {
		margin: 0;
		font-size: 16px;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* Error state */
	.error {
		padding: var(--space-5);
		border-radius: var(--radius-md);
		background: var(--color-danger-soft);
		color: var(--color-danger);
		text-align: center;
	}

	.error p {
		margin: 0 0 var(--space-3);
		font-size: 16px;
	}

	.error .actions {
		display: flex;
		justify-content: center;
		gap: var(--space-2);
	}

	.error .primary,
	.error .secondary {
		border-radius: var(--radius-sm);
		padding: var(--space-2) var(--space-4);
		font-weight: 600;
		font-size: 15px;
		border: 1px solid transparent;
	}

	.error .primary {
		background: var(--color-danger);
		color: white;
	}

	.error .secondary {
		background: none;
		border-color: currentColor;
		color: var(--color-danger);
	}
</style>
