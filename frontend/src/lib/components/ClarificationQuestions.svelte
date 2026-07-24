<script lang="ts">
	import { mealFlow } from '$lib/stores/meal-flow.svelte';
</script>

<section class="clarify">
	<h2>Quick check before I estimate nutrition</h2>
	<p class="subtitle">The photo alone leaves these ambiguous — pick the closest answer.</p>

	<ul>
		{#each mealFlow.questions as q (q.question_id)}
			<li class="question">
				<p class="prompt">{q.question}</p>
				<div class="options">
					{#each q.options as option (option)}
						<label class="option" class:selected={mealFlow.answers[q.question_id] === option}>
							<input
								type="radio"
								name={q.question_id}
								value={option}
								checked={mealFlow.answers[q.question_id] === option}
								onchange={() => mealFlow.setAnswer(q.question_id, option)}
							/>
							{option}
						</label>
					{/each}
				</div>
			</li>
		{/each}
	</ul>

	<div class="actions">
		<button type="button" class="secondary" onclick={() => mealFlow.reset()}>Start over</button>
		<button type="button" class="primary" onclick={() => mealFlow.submitClarification()}>
			Continue
		</button>
	</div>
</section>

<style>
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
		gap: var(--space-4);
	}

	.question {
		padding: var(--space-3);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
	}

	.prompt {
		margin: 0 0 var(--space-2);
		font-weight: 600;
	}

	.options {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	.option {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		padding: var(--space-1) var(--space-3);
		border: 1px solid var(--color-border);
		border-radius: 999px;
		font-size: 15px;
		cursor: pointer;
	}

	.option.selected {
		border-color: var(--color-accent);
		background: var(--color-accent-soft);
	}

	.option input {
		accent-color: var(--color-accent);
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
		background: var(--color-bg);
	}
</style>
