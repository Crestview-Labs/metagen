/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * A single tool call request from the LLM.
 */
export type ToolCallRequest = {
    tool_id: string;
    tool_name: string;
    tool_args: Record<string, any>;
};

