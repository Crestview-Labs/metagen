/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ToolInfo } from './ToolInfo.js';
/**
 * System information response.
 */
export type SystemInfo = {
    agent_name: string;
    model: string;
    tools: Array<ToolInfo>;
    tool_count: number;
    memory_path: string;
    initialized: boolean;
};

