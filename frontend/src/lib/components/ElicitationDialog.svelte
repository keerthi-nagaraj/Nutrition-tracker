<script lang="ts">
	import { mcp } from '$lib/mcp/client.svelte';

	let textValue = $state('');

	const pending = $derived(mcp.pendingElicitation);
	const valueSchema = $derived(
		pending?.schema.properties
			? ((pending.schema.properties as Record<string, unknown>).value as
					| Record<string, unknown>
					| undefined)
			: undefined
	);
	const options = $derived((valueSchema?.enum as string[] | undefined) ?? null);

	$effect(() => {
		if (pending) textValue = '';
	});

	function chooseOption(value: string) {
		pending?.respond({ action: 'accept', content: { value } });
	}

	function submitText() {
		if (!pending || !textValue.trim()) return;
		pending.respond({ action: 'accept', content: { value: textValue } });
	}

	function cancel() {
		pending?.respond({ action: 'cancel' });
	}
</script>

{#if pending}
	<div class="backdrop" role="presentation">
		<div class="dialog" role="dialog" aria-modal="true" aria-label="Confirmation needed">
			<p class="message">{pending.message}</p>

			{#if options}
				<div class="options">
					{#each options as option (option)}
						<button type="button" class="option" onclick={() => chooseOption(option)}>
							{option}
						</button>
					{/each}
				</div>
				<div class="actions">
					<button type="button" class="secondary" onclick={cancel}>Cancel</button>
				</div>
			{:else}
				<form
					onsubmit={(e) => {
						e.preventDefault();
						submitText();
					}}
				>
					<textarea bind:value={textValue} rows="3" placeholder="Type your answer…"></textarea>
					<div class="actions">
						<button type="button" class="secondary" onclick={cancel}>Cancel</button>
						<button type="submit" class="primary" disabled={!textValue.trim()}>Submit</button>
					</div>
				</form>
			{/if}
		</div>
	</div>
{/if}

<style>
	.backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.45);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-5);
	}

	.dialog {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-md);
		padding: var(--space-5);
		width: 100%;
		max-width: 420px;
	}

	.message {
		margin: 0 0 var(--space-4);
		font-size: 16px;
		white-space: pre-line;
	}

	.options {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
	}

	.option {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-bg);
		color: var(--color-text);
		padding: var(--space-2) var(--space-3);
		text-align: left;
		font-size: 15px;
		font-weight: 600;
	}

	.option:hover {
		border-color: var(--color-accent);
		background: var(--color-accent-soft);
	}

	textarea {
		width: 100%;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-bg);
		color: var(--color-text);
		padding: var(--space-2);
		font: inherit;
		resize: vertical;
	}

	.actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-2);
		margin-top: var(--space-3);
	}

	.primary,
	.secondary {
		border-radius: var(--radius-sm);
		padding: var(--space-2) var(--space-4);
		font-weight: 600;
		font-size: 15px;
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
		background: var(--color-bg);
	}
</style>
