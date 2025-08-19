/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Authentication status response.
 */
export type AuthStatus = {
    authenticated: boolean;
    user_info?: (Record<string, string> | null);
    services?: Array<string>;
    provider?: (string | null);
};

