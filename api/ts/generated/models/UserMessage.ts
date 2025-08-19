/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MessageType } from './MessageType.js';
/**
 * User chat message.
 */
export type UserMessage = {
    type?: MessageType;
    timestamp?: string;
    agent_id?: string;
    session_id: string;
    content: string;
};

