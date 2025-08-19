/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MessageType } from './MessageType.js';
import type { ToolCallRequest } from './ToolCallRequest.js';
/**
 * LLM wants to call tools - contains all tool call details.
 */
export type ToolCallMessage = {
    type?: MessageType;
    timestamp?: string;
    agent_id?: string;
    session_id: string;
    tool_calls: Array<ToolCallRequest>;
};

