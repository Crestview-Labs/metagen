export declare function createTestProfile(name: string): Promise<string>;
export declare function cleanTestProfile(name: string): Promise<void>;
export declare function mockSpawn(): {
    pid: number;
    stdout: {
        pipe: any;
        on: any;
    };
    stderr: {
        pipe: any;
        on: any;
    };
    on: any;
    kill: any;
};
