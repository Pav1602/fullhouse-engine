/**
 * PixelRobot — 16×16 pixel-art robot rendered as inline SVG.
 *
 * No external assets. Just rectangles. Scales cleanly to any size via
 * `size` prop or CSS; `shape-rendering: crispEdges` keeps pixels sharp.
 *
 * Usage:
 *   <PixelRobot avatar="robot_2" hat="crown" size={96} />
 */

import React from "react";

// --- Palettes ---------------------------------------------------------------

type Palette = {
  body: string;     // main head fill
  shade: string;    // darker edge / shadow
  highlight: string;// lighter speck
  visor: string;    // eye strip background
  eye: string;      // pupil / light colour
};

export const AVATAR_KEYS = [
  "robot_1", "robot_2", "robot_3", "robot_4",
  "robot_5", "robot_6", "robot_7", "robot_8",
] as const;
export type AvatarKey = typeof AVATAR_KEYS[number];

export const AVATAR_PALETTES: Record<AvatarKey, Palette> = {
  robot_1: { body: "#4ECDC4", shade: "#2B8A85", highlight: "#B8F2EE", visor: "#1E1E1E", eye: "#FFE66D" }, // teal
  robot_2: { body: "#FF8C61", shade: "#C85C34", highlight: "#FFCBB4", visor: "#1E1E1E", eye: "#FFFFFF" }, // coral
  robot_3: { body: "#E84A9A", shade: "#9F2664", highlight: "#FFB8DE", visor: "#1E1E1E", eye: "#A7F0FF" }, // pink
  robot_4: { body: "#FFD93D", shade: "#C19E11", highlight: "#FFF3B0", visor: "#1E1E1E", eye: "#3A86FF" }, // yellow
  robot_5: { body: "#8A63D2", shade: "#533884", highlight: "#CFB8F4", visor: "#1E1E1E", eye: "#FFE66D" }, // purple
  robot_6: { body: "#6BCB77", shade: "#398943", highlight: "#BEEAC4", visor: "#1E1E1E", eye: "#FFFFFF" }, // lime
  robot_7: { body: "#3A86FF", shade: "#1F4D9E", highlight: "#A8C8FF", visor: "#1E1E1E", eye: "#FFD93D" }, // navy
  robot_8: { body: "#F2F1F0", shade: "#9E9D9A", highlight: "#FFFFFF", visor: "#1E1E1E", eye: "#FF6B6B" }, // ghost
};

// --- Hats --------------------------------------------------------------------

export const HAT_KEYS = [
  "none", "crown", "tophat", "beanie",
  "cap", "party", "graduate", "cowboy", "wizard",
] as const;
export type HatKey = typeof HAT_KEYS[number];

export const HAT_LABELS: Record<HatKey, string> = {
  none: "No hat",
  crown: "Crown",
  tophat: "Top hat",
  beanie: "Beanie",
  cap: "Cap",
  party: "Party hat",
  graduate: "Graduate cap",
  cowboy: "Cowboy hat",
  wizard: "Wizard hat",
};

// Each hat is an array of <rect> specs drawn OVER the robot head.
// Grid is 16×16. y=0 is the top. The head starts at y=2 so hats live at y=0–3.
type PixelRect = { x: number; y: number; w?: number; h?: number; fill: string };

const HATS: Record<HatKey, PixelRect[]> = {
  none: [],
  crown: [
    { x: 4,  y: 1, w: 1, h: 2, fill: "#FFD93D" },
    { x: 6,  y: 0, w: 1, h: 3, fill: "#FFD93D" },
    { x: 8,  y: 0, w: 1, h: 3, fill: "#FFD93D" },
    { x: 10, y: 0, w: 1, h: 3, fill: "#FFD93D" },
    { x: 11, y: 1, w: 1, h: 2, fill: "#FFD93D" },
    { x: 3,  y: 2, w: 10, h: 1, fill: "#E1B709" },
    { x: 7,  y: 1, w: 1, h: 1, fill: "#E84A9A" },
    { x: 9,  y: 1, w: 1, h: 1, fill: "#4ECDC4" },
  ],
  tophat: [
    { x: 3, y: 3, w: 10, h: 1, fill: "#1A1A1A" }, // brim
    { x: 4, y: 0, w:  8, h: 3, fill: "#1A1A1A" }, // body
    { x: 4, y: 2, w:  8, h: 1, fill: "#E84A9A" }, // band
  ],
  beanie: [
    { x: 3, y: 3, w: 10, h: 1, fill: "#C85C34" },
    { x: 3, y: 2, w: 10, h: 1, fill: "#FF8C61" },
    { x: 4, y: 1, w:  8, h: 1, fill: "#FF8C61" },
    { x: 5, y: 0, w:  6, h: 1, fill: "#FF8C61" },
    { x: 7, y: 1, w:  2, h: 1, fill: "#FFFFFF" }, // pom
    { x: 5, y: 2, w:  2, h: 1, fill: "#C85C34" },
    { x: 9, y: 2, w:  2, h: 1, fill: "#C85C34" },
  ],
  cap: [
    { x: 3, y: 3, w: 10, h: 1, fill: "#3A86FF" },
    { x: 4, y: 2, w:  8, h: 1, fill: "#3A86FF" },
    { x: 5, y: 1, w:  6, h: 1, fill: "#3A86FF" },
    { x: 6, y: 0, w:  5, h: 1, fill: "#3A86FF" },
    { x: 11,y: 3, w:  3, h: 1, fill: "#1F4D9E" }, // brim jut
  ],
  party: [
    { x: 7, y: 0, w: 2, h: 1, fill: "#4ECDC4" },
    { x: 7, y: 1, w: 2, h: 1, fill: "#FFD93D" },
    { x: 6, y: 2, w: 4, h: 1, fill: "#E84A9A" },
    { x: 5, y: 3, w: 6, h: 1, fill: "#4ECDC4" },
    { x: 8, y: 0, w: 1, h: 1, fill: "#FFFFFF" }, // pom
  ],
  graduate: [
    { x: 3, y: 2, w: 10, h: 1, fill: "#1A1A1A" }, // board
    { x: 4, y: 3, w:  8, h: 1, fill: "#2A2A2A" }, // cap
    { x: 12, y: 2, w: 1, h: 1, fill: "#FFD93D" }, // tassel anchor
    { x: 13, y: 2, w: 1, h: 3, fill: "#FFD93D" }, // tassel
  ],
  cowboy: [
    { x: 2, y: 3, w: 12, h: 1, fill: "#8B4513" }, // wide brim
    { x: 4, y: 2, w:  8, h: 1, fill: "#8B4513" },
    { x: 5, y: 1, w:  6, h: 1, fill: "#A0522D" },
    { x: 6, y: 0, w:  4, h: 1, fill: "#A0522D" },
    { x: 5, y: 1, w:  6, h: 1, fill: "#A0522D" },
    { x: 4, y: 2, w:  8, h: 1, fill: "#8B4513" },
  ],
  wizard: [
    { x: 7, y: 0, w: 2, h: 1, fill: "#533884" },
    { x: 6, y: 1, w: 4, h: 1, fill: "#533884" },
    { x: 5, y: 2, w: 6, h: 1, fill: "#8A63D2" },
    { x: 4, y: 3, w: 8, h: 1, fill: "#8A63D2" },
    { x: 7, y: 2, w: 1, h: 1, fill: "#FFD93D" }, // star
    { x: 9, y: 1, w: 1, h: 1, fill: "#FFFFFF" }, // star
  ],
};

// --- Robot head geometry (16×16 grid, head occupies y=2..14) -----------------

function robotHead(p: Palette): PixelRect[] {
  return [
    // antenna
    { x: 7,  y: 2, w: 2, h: 1, fill: p.shade },
    { x: 7,  y: 3, w: 2, h: 1, fill: p.body },

    // top row curve
    { x: 4,  y: 4, w: 8, h: 1, fill: p.shade },
    // main head block
    { x: 3,  y: 5, w: 10, h: 7, fill: p.body },
    // bottom curve
    { x: 4,  y: 12, w: 8, h: 1, fill: p.shade },

    // highlights (upper-left gleam)
    { x: 4,  y: 5, w: 2, h: 1, fill: p.highlight },
    { x: 4,  y: 6, w: 1, h: 1, fill: p.highlight },

    // visor strip
    { x: 4,  y: 7, w: 8, h: 3, fill: p.visor },

    // eyes
    { x: 5,  y: 8, w: 2, h: 1, fill: p.eye },
    { x: 9,  y: 8, w: 2, h: 1, fill: p.eye },

    // mouth / speaker grille
    { x: 6,  y: 11, w: 4, h: 1, fill: p.shade },
    { x: 7,  y: 11, w: 1, h: 1, fill: p.visor },
    { x: 8,  y: 11, w: 1, h: 1, fill: p.visor },

    // ears / bolts
    { x: 2,  y: 8, w: 1, h: 2, fill: p.shade },
    { x: 13, y: 8, w: 1, h: 2, fill: p.shade },
  ];
}

// --- Component ---------------------------------------------------------------

export interface PixelRobotProps {
  avatar?: AvatarKey | string;
  hat?: HatKey | string;
  size?: number;
  className?: string;
  title?: string;
}

export function PixelRobot({
  avatar = "robot_1",
  hat = "none",
  size = 64,
  className,
  title,
}: PixelRobotProps) {
  const palette = AVATAR_PALETTES[avatar as AvatarKey] ?? AVATAR_PALETTES.robot_1;
  const hatRects = HATS[hat as HatKey] ?? HATS.none;
  const head = robotHead(palette);

  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      shapeRendering="crispEdges"
      className={className}
      role="img"
      aria-label={title ?? `Pixel robot ${avatar}${hat && hat !== "none" ? ` wearing ${hat}` : ""}`}
    >
      {title ? <title>{title}</title> : null}
      {head.map((r, i) => (
        <rect key={`h${i}`} x={r.x} y={r.y} width={r.w ?? 1} height={r.h ?? 1} fill={r.fill} />
      ))}
      {hatRects.map((r, i) => (
        <rect key={`t${i}`} x={r.x} y={r.y} width={r.w ?? 1} height={r.h ?? 1} fill={r.fill} />
      ))}
    </svg>
  );
}

export default PixelRobot;
