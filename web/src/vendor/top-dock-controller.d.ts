// Types for the vendored ThreeUI top-dock controller (MIT, Meng To).
export type TopDockAxis = "x" | "y";
export type TopDockOptions = {
    proximity: number;
    spring: number;
    damping: number;
    widthGrowth: number;
    heightGrowth: number;
    drop: number;
    axis?: TopDockAxis;
    distribute?: boolean;
    lockTrack?: boolean;
};
export declare function createTopDockController(root: HTMLElement, getOptions: () => TopDockOptions): () => void;
