import { jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { Text } from 'ink';
const spinnerFrames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
export const Spinner = ({ message = 'Processing' }) => {
    const [frame, setFrame] = useState(0);
    useEffect(() => {
        const interval = setInterval(() => {
            setFrame((prev) => (prev + 1) % spinnerFrames.length);
        }, 80);
        return () => clearInterval(interval);
    }, []);
    return (_jsxs(Text, { color: "cyan", children: [spinnerFrames[frame], " ", message, "..."] }));
};
export default Spinner;
