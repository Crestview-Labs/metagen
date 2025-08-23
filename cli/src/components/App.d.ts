/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */
import React from 'react';
interface AppProps {
    initialMessage?: string;
    autoApproveTools?: boolean;
    exitOnComplete?: boolean;
    minimalUI?: boolean;
}
export declare const App: React.FC<AppProps>;
export default App;
