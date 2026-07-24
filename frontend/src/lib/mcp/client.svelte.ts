import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { ElicitRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import type { ElicitResult } from '@modelcontextprotocol/sdk/types.js';
import { browser } from '$app/environment';

const MCP_SERVER_URL = import.meta.env.VITE_MCP_SERVER_URL || 'http://127.0.0.1:8000/mcp';

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'error';

interface ToolContentPart {
	type: string;
	text?: string;
}

interface ToolCallResult {
	content?: ToolContentPart[];
	structuredContent?: unknown;
	isError?: boolean;
}

function extractText(result: ToolCallResult): string | null {
	return result.content?.find((part) => part.type === 'text')?.text ?? null;
}

/** A server-initiated `elicitation/create` request awaiting a human answer.
 *  Only form-mode requests are handled — see ElicitationDialog.svelte. */
export interface PendingElicitation {
	message: string;
	schema: Record<string, unknown>;
	respond: (result: ElicitResult) => void;
}

/** Thin reactive wrapper around one MCP session over Streamable HTTP. */
class McpConnection {
	status = $state<ConnectionStatus>('idle');
	errorMessage = $state<string | null>(null);
	/** Set while a server tool call (e.g. analyze_meal) is waiting on a real
	 *  MCP elicitation round trip — ElicitationDialog.svelte renders this. */
	pendingElicitation = $state<PendingElicitation | null>(null);

	#client: Client | null = null;
	#connecting: Promise<Client> | null = null;

	async #ensureClient(): Promise<Client> {
		if (!browser) throw new Error('The MCP client only runs in the browser.');
		if (this.#client) return this.#client;
		if (this.#connecting) return this.#connecting;

		this.status = 'connecting';
		this.errorMessage = null;

		this.#connecting = (async () => {
			const transport = new StreamableHTTPClientTransport(new URL(MCP_SERVER_URL));
			const client = new Client(
				{ name: 'nutrition-tracker-web', version: '1.0.0' },
				{ capabilities: { elicitation: {} } }
			);

			// Registered before connect() so no request can arrive un-handled.
			// Only form-mode (message + requestedSchema) is supported — this
			// app has no use for URL-mode elicitation, so that's declined.
			client.setRequestHandler(ElicitRequestSchema, (request) => {
				const params = request.params;
				if (!('requestedSchema' in params)) {
					return Promise.resolve({ action: 'decline' } as ElicitResult);
				}
				return new Promise<ElicitResult>((resolve) => {
					this.pendingElicitation = {
						message: params.message,
						schema: params.requestedSchema as Record<string, unknown>,
						respond: (result) => {
							this.pendingElicitation = null;
							resolve(result);
						}
					};
				});
			});

			try {
				await client.connect(transport);
				this.#client = client;
				this.status = 'connected';
				return client;
			} catch (err) {
				this.status = 'error';
				this.errorMessage = err instanceof Error ? err.message : String(err);
				this.#connecting = null;
				throw err;
			}
		})();

		return this.#connecting;
	}

	/** Calls an MCP tool and decodes its structured (or JSON text) result as T. */
	async callTool<T>(name: string, args: Record<string, unknown>): Promise<T> {
		const client = await this.#ensureClient();
		const result = (await client.callTool({ name, arguments: args })) as ToolCallResult;

		if (result.isError) {
			throw new Error(extractText(result) ?? `Tool "${name}" failed.`);
		}
		if (result.structuredContent !== undefined) {
			return result.structuredContent as T;
		}
		const text = extractText(result);
		if (text) {
			try {
				return JSON.parse(text) as T;
			} catch {
				/* fall through to the error below */
			}
		}
		throw new Error(`Tool "${name}" returned no usable content.`);
	}

	async reconnect() {
		this.disconnect();
		await this.#ensureClient();
	}

	disconnect() {
		this.#client?.close();
		this.#client = null;
		this.#connecting = null;
		this.status = 'idle';
		this.pendingElicitation?.respond({ action: 'cancel' });
	}
}

export const mcp = new McpConnection();
