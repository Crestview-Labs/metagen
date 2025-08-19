/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MessageType } from './MessageType.js';
/**
 * Agent requests approval for a specific tool.
 */
export type ApprovalRequestMessage = {
    type?: MessageType;
    timestamp?: string;
    agent_id?: string;
    session_id: string;
    tool_id: string;
    tool_name: string;
    tool_args: Record<string, any>;
};

