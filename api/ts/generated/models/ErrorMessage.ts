/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MessageType } from './MessageType.js';
/**
 * Error message from agent.
 */
export type ErrorMessage = {
    type?: MessageType;
    timestamp?: string;
    agent_id?: string;
    session_id: string;
    error: string;
    details?: (Record<string, any> | null);
};

