/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Types of messages in the system.
 */
export enum MessageType {
    USER = 'user',
    AGENT = 'agent',
    SYSTEM = 'system',
    THINKING = 'thinking',
    TOOL_CALL = 'tool_call',
    APPROVAL_REQUEST = 'approval_request',
    APPROVAL_RESPONSE = 'approval_response',
    TOOL_STARTED = 'tool_started',
    TOOL_RESULT = 'tool_result',
    TOOL_ERROR = 'tool_error',
    USAGE = 'usage',
    ERROR = 'error',
}
