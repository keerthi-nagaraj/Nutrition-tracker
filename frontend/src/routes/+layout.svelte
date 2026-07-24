<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import ElicitationDialog from '$lib/components/ElicitationDialog.svelte';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="round-viewport">
	<div class="round-content">
		{@render children()}
	</div>
</div>

<ElicitationDialog />

<style>
	.round-viewport {
		width: 1080px;
		height: 1080px;
		flex-shrink: 0;
		border-radius: 50%;
		overflow-y: auto;
		overflow-x: hidden;
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		box-shadow: var(--shadow-md);

		/* Hide the scrollbar so a round bezel doesn't get a square scroll
		   track poking out of it; the content still scrolls with wheel/touch. */
		scrollbar-width: none;
		-ms-overflow-style: none;
	}

	.round-viewport::-webkit-scrollbar {
		display: none;
	}

	.round-content {
		min-height: 100%;
		display: flex;
		flex-direction: column;
		justify-content: center;

		/* Inscribed-square safe area: a 1080-diameter circle safely fits a
		   ~760px square, so content is capped well inside that and padded
		   away from the curve top/bottom instead of touching it. */
		max-width: 720px;
		margin: 0 auto;
		padding: 120px 32px;
	}
</style>
