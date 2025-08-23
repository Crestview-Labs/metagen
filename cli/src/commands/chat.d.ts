/**
 * Chat command with auto-start backend support
 * Each CLI instance gets its own session, even when sharing a backend
 */
interface ChatOptions {
    profile?: string;
    message?: string;
    autoApprove?: boolean;
    noAutoStart?: boolean;
}
export declare function chatCommand(options?: ChatOptions): Promise<void>;
export {};
