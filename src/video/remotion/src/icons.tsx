import React from "react";

export type IconName =
  | "sun"
  | "brain"
  | "puzzle"
  | "toolbox"
  | "briefcase"
  | "settings"
  | "monitor"
  | "flask"
  | "sparkles"
  | "megaphone"
  | "layers-3"
  | "compass"
  | "smartphone"
  | "cloud"
  | "globe"
  | "file-text"
  | "mic"
  | "music-4"
  | "shield-alert"
  | "masks"
  | "car"
  | "link-2"
  | "radio";

const common = (size: number, color: string, strokeWidth: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: color,
  strokeWidth,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const Icon: React.FC<{
  name: IconName;
  size?: number;
  color?: string;
  strokeWidth?: number;
  style?: React.CSSProperties;
}> = ({ name, size = 24, color = "currentColor", strokeWidth = 1.8, style }) => {
  const props = common(size, color, strokeWidth);

  return (
    <svg {...props} style={style}>
      {name === "sun" ? (
        <>
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.5v2.7" />
          <path d="M12 18.8v2.7" />
          <path d="m4.93 4.93 1.91 1.91" />
          <path d="m17.16 17.16 1.91 1.91" />
          <path d="M2.5 12h2.7" />
          <path d="M18.8 12h2.7" />
          <path d="m4.93 19.07 1.91-1.91" />
          <path d="m17.16 6.84 1.91-1.91" />
        </>
      ) : null}

      {name === "brain" ? (
        <>
          <path d="M9.3 5.1a3 3 0 0 1 5.4 1.3 2.8 2.8 0 0 1 2.3 3.2 3 3 0 0 1 1.1 4.7 3.1 3.1 0 0 1-2.3 5.4H9.5a3.1 3.1 0 0 1-2.8-4.3 3 3 0 0 1-1-5 2.9 2.9 0 0 1 1.9-3.9 3 3 0 0 1 1.7-1.4Z" />
          <path d="M10 8.4v7.2" />
          <path d="M14 8.4v7.2" />
          <path d="M8.1 11.4H10" />
          <path d="M14 11.4h1.9" />
          <path d="M9.8 15.6h4.4" />
        </>
      ) : null}

      {name === "puzzle" ? (
        <>
          <path d="M9.1 4.1h3.2a1.2 1.2 0 0 1 1.2 1.2v1a1.8 1.8 0 1 0 2.6 1.6v-.3h1.6a1.2 1.2 0 0 1 1.2 1.2v3.1h-1a1.8 1.8 0 1 0 0 2.6h1v3a1.2 1.2 0 0 1-1.2 1.2h-3.1v-1a1.8 1.8 0 1 0-2.6 0v1H9.1a1.2 1.2 0 0 1-1.2-1.2v-3H6.8a1.8 1.8 0 1 0 0-2.6h1.1V5.3a1.2 1.2 0 0 1 1.2-1.2Z" />
        </>
      ) : null}

      {name === "toolbox" ? (
        <>
          <path d="M4 9.2h16a1.8 1.8 0 0 1 1.8 1.8v6.6A1.8 1.8 0 0 1 20 19.4H4a1.8 1.8 0 0 1-1.8-1.8V11A1.8 1.8 0 0 1 4 9.2Z" />
          <path d="M9.2 9.2V7.1A1.9 1.9 0 0 1 11.1 5.2h1.8A1.9 1.9 0 0 1 14.8 7.1v2.1" />
          <path d="M2.2 13.1h19.6" />
          <path d="M10.2 13.1v1.3h3.6v-1.3" />
        </>
      ) : null}

      {name === "briefcase" ? (
        <>
          <rect x="4" y="7.6" width="16" height="10.6" rx="2" />
          <path d="M9.1 7.6V5.8A1.8 1.8 0 0 1 10.9 4h2.2a1.8 1.8 0 0 1 1.8 1.8v1.8" />
          <path d="M4 11.7h16" />
          <rect x="10.6" y="11.1" width="2.8" height="2.3" rx="0.4" />
        </>
      ) : null}

      {name === "settings" ? (
        <>
          <circle cx="12" cy="12" r="3.1" />
          <path d="M19.1 12a7.3 7.3 0 0 0-.1-1.2l2-1.5-2-3.5-2.4 1a7.5 7.5 0 0 0-2-1.2l-.3-2.6H10l-.3 2.6a7.5 7.5 0 0 0-2 1.2l-2.4-1-2 3.5 2 1.5a7.3 7.3 0 0 0 0 2.4l-2 1.5 2 3.5 2.4-1a7.5 7.5 0 0 0 2 1.2l.3 2.6h4l.3-2.6a7.5 7.5 0 0 0 2-1.2l2.4 1 2-3.5-2-1.5c.1-.4.1-.8.1-1.2Z" />
        </>
      ) : null}

      {name === "monitor" ? (
        <>
          <rect x="3.2" y="4.2" width="17.6" height="11.9" rx="1.8" />
          <path d="M8.4 19.8h7.2" />
          <path d="M12 16.1v3.7" />
        </>
      ) : null}

      {name === "flask" ? (
        <>
          <path d="M10 3.5h4" />
          <path d="M11 3.5v4.2l-4.7 7.5a3 3 0 0 0 2.5 4.6h6.4a3 3 0 0 0 2.5-4.6L13 7.7V3.5" />
          <path d="M8.1 14.3h7.8" />
        </>
      ) : null}

      {name === "sparkles" ? (
        <>
          <path d="M12 3.5 13.3 8l4.2 1.3-4.2 1.3L12 15l-1.3-4.4L6.5 9.3 10.7 8 12 3.5Z" />
          <path d="m18.2 14.2.7 2.1 2.1.7-2.1.7-.7 2.1-.7-2.1-2.1-.7 2.1-.7.7-2.1Z" />
          <path d="m5.2 14.6.6 1.8 1.8.6-1.8.6-.6 1.8-.6-1.8-1.8-.6 1.8-.6.6-1.8Z" />
        </>
      ) : null}

      {name === "megaphone" ? (
        <>
          <path d="M4.3 11.4v-2.8a1.8 1.8 0 0 1 1.8-1.8h1.6l7-3.2a1 1 0 0 1 1.4.9v14.8a1 1 0 0 1-1.4.9l-7-3.2H6.1a1.8 1.8 0 0 1-1.8-1.8Z" />
          <path d="m8.2 16.9 1.4 3.2" />
          <path d="M18.2 8.1a4.1 4.1 0 0 1 0 7.8" />
        </>
      ) : null}

      {name === "layers-3" ? (
        <>
          <path d="m12 4.1 7.8 4.2L12 12.5 4.2 8.3 12 4.1Z" />
          <path d="m4.2 12.1 7.8 4.2 7.8-4.2" />
          <path d="m4.2 15.9 7.8 4 7.8-4" />
        </>
      ) : null}

      {name === "compass" ? (
        <>
          <circle cx="12" cy="12" r="8.7" />
          <path d="m9.1 14.9 1.8-5 5-1.8-1.8 5Z" />
          <path d="m10.9 9.9 3.2 3.2" />
        </>
      ) : null}

      {name === "smartphone" ? (
        <>
          <rect x="7" y="2.8" width="10" height="18.4" rx="2.3" />
          <path d="M10.2 5.8h3.6" />
          <circle cx="12" cy="17.7" r="0.8" />
        </>
      ) : null}

      {name === "cloud" ? (
        <>
          <path d="M6.6 18a4.1 4.1 0 1 1 .8-8.1 5.3 5.3 0 0 1 10.1 1.5A3.5 3.5 0 1 1 18 18Z" />
        </>
      ) : null}

      {name === "globe" ? (
        <>
          <circle cx="12" cy="12" r="8.7" />
          <path d="M3.3 12h17.4" />
          <path d="M12 3.3a12.3 12.3 0 0 1 0 17.4" />
          <path d="M12 3.3a12.3 12.3 0 0 0 0 17.4" />
          <path d="M5.8 7.6c1.7 1 3.9 1.5 6.2 1.5s4.5-.5 6.2-1.5" />
          <path d="M5.8 16.4c1.7-1 3.9-1.5 6.2-1.5s4.5.5 6.2 1.5" />
        </>
      ) : null}

      {name === "file-text" ? (
        <>
          <path d="M14 2.8H7.7a1.9 1.9 0 0 0-1.9 1.9v14.6a1.9 1.9 0 0 0 1.9 1.9h8.6a1.9 1.9 0 0 0 1.9-1.9V8.5Z" />
          <path d="M14 2.8v5.7h5.7" />
          <path d="M9.2 12.1h5.8" />
          <path d="M9.2 15.6h5.8" />
        </>
      ) : null}

      {name === "mic" ? (
        <>
          <path d="M12 15a3 3 0 0 0 3-3V7a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" />
          <path d="M7.8 11.5a4.2 4.2 0 0 0 8.4 0" />
          <path d="M12 15v4.2" />
          <path d="M9.4 19.2h5.2" />
        </>
      ) : null}

      {name === "music-4" ? (
        <>
          <path d="M9 18V6.6l8-1.8v11.5" />
          <circle cx="7.2" cy="18.4" r="2.2" />
          <circle cx="17" cy="16.6" r="2.2" />
        </>
      ) : null}

      {name === "shield-alert" ? (
        <>
          <path d="M12 3.1 5.8 5.6v5.7c0 4.1 2.5 7.9 6.2 9.6 3.7-1.7 6.2-5.5 6.2-9.6V5.6Z" />
          <path d="M12 8.1v4.9" />
          <circle cx="12" cy="16.6" r="0.7" />
        </>
      ) : null}

      {name === "masks" ? (
        <>
          <path d="M6.7 7.2c1.9 1.1 4.8 1.1 7 0 2.2-1.1 4.5-1.2 6.1-.2-.4 5.4-3.2 8.6-7.5 8.6S5.8 12.4 5.2 7c.5-.1 1 .1 1.5.2Z" />
          <path d="M7.7 11.1c.8.5 1.6.7 2.4.7s1.6-.2 2.4-.7" />
          <path d="M11.3 16.1c1.5 1.4 3.6 2 5.8 1.6 1.1-.2 2.1-.7 2.9-1.3" />
        </>
      ) : null}

      {name === "car" ? (
        <>
          <path d="M6.3 16.8h11.4a2 2 0 0 0 1.9-1.5l.7-3a2 2 0 0 0-1.9-2.5h-1.3l-1.4-3H8.3l-1.4 3H5.6a2 2 0 0 0-1.9 2.5l.7 3a2 2 0 0 0 1.9 1.5Z" />
          <circle cx="7.7" cy="16.8" r="1.6" />
          <circle cx="16.3" cy="16.8" r="1.6" />
          <path d="M6.8 9.8h10.4" />
        </>
      ) : null}

      {name === "link-2" ? (
        <>
          <path d="M10.4 13.6 8.2 15.8a3 3 0 0 1-4.2-4.2l2.5-2.5A3 3 0 0 1 10.7 11" />
          <path d="m13.6 10.4 2.2-2.2a3 3 0 0 1 4.2 4.2l-2.5 2.5A3 3 0 0 1 13.3 13" />
          <path d="m8.9 15.1 6.2-6.2" />
        </>
      ) : null}

      {name === "radio" ? (
        <>
          <path d="M5.2 8.2h13.6a1.6 1.6 0 0 1 1.6 1.6v8.2a1.6 1.6 0 0 1-1.6 1.6H5.2a1.6 1.6 0 0 1-1.6-1.6V9.8a1.6 1.6 0 0 1 1.6-1.6Z" />
          <path d="m9.2 4.1 8.9 4.1" />
          <circle cx="8.1" cy="13.9" r="2.1" />
          <path d="M13.2 13.1h4.1" />
          <path d="M13.2 16.2h4.1" />
        </>
      ) : null}
    </svg>
  );
};
