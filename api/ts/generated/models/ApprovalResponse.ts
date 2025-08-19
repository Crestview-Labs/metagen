/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApprovalDecision } from './ApprovalDecision.js';
/**
 * Response from the approval endpoint.
 */
export type ApprovalResponse = {
    /**
     * ID of the tool that was approved/rejected
     */
    tool_id: string;
    /**
     * The approval decision that was processed
     */
    decision: ApprovalDecision;
    /**
     * Optional status message
     */
    message?: (string | null);
};

