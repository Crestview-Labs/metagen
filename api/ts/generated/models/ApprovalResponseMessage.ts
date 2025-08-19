/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApprovalDecision } from './ApprovalDecision.js';
import type { MessageType } from './MessageType.js';
/**
 * User responds to approval request.
 */
export type ApprovalResponseMessage = {
    type?: MessageType;
    timestamp?: string;
    agent_id?: string;
    session_id: string;
    tool_id: string;
    decision: ApprovalDecision;
    feedback?: (string | null);
};

