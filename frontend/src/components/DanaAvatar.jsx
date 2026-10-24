/** Illustrated avatar for Dana Reyes, EOC public-information officer.
 *  Blinks on its own; the mouth moves while she is speaking. */
export default function DanaAvatar({ mood = 'calm', speaking = false, size = 112 }) {
  return (
    <div className={`avatar mood-${mood} ${speaking ? 'speaking' : ''}`} style={{ width: size, height: size }}>
      <svg viewBox="0 0 120 120" role="img" aria-label="Dana Reyes">
        <defs>
          <linearGradient id="dana-bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#1e2a3a" /><stop offset="1" stopColor="#0f1722" />
          </linearGradient>
          <linearGradient id="dana-skin" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#d7a27c" /><stop offset="1" stopColor="#c18b66" />
          </linearGradient>
          <clipPath id="dana-clip"><circle cx="60" cy="60" r="56" /></clipPath>
        </defs>
        <circle cx="60" cy="60" r="56" fill="url(#dana-bg)" />
        <g clipPath="url(#dana-clip)">
          {/* hair back */}
          <path d="M28 62c0-24 14-38 32-38s32 14 32 38v26H28z" fill="#2b1d17" />
          {/* shoulders + EOC vest */}
          <path d="M18 120c2-20 18-30 42-30s40 10 42 30z" fill="#e8743b" />
          <path d="M48 92l12 14 12-14" fill="none" stroke="#f7d9c4" strokeWidth="3" strokeLinecap="round" />
          <rect x="42" y="104" width="36" height="5" rx="2.5" fill="#f5f0e6" opacity=".9" />
          {/* neck */}
          <path d="M52 78h16v14c-4 3-12 3-16 0z" fill="#b97f5c" />
          {/* face */}
          <ellipse cx="60" cy="60" rx="21" ry="24" fill="url(#dana-skin)" />
          {/* fringe */}
          <path d="M38 54c2-16 12-24 24-24 10 0 19 6 21 20-9-2-18-8-23-14-5 9-13 15-22 18z" fill="#3a2820" />
          {/* brows */}
          <path className="brow" d="M46 52q5-3 10 0M64 52q5-3 10 0" stroke="#2b1d17" strokeWidth="2.2" fill="none" strokeLinecap="round" />
          {/* eyes */}
          <g className="eyes"><ellipse cx="51" cy="59" rx="2.6" ry="3" fill="#1b1410" /><ellipse cx="69" cy="59" rx="2.6" ry="3" fill="#1b1410" /></g>
          {/* nose + cheeks */}
          <path d="M60 62q-2 6 1 7" stroke="#a8704f" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          <circle cx="47" cy="68" r="3.5" fill="#e08f78" opacity=".35" /><circle cx="73" cy="68" r="3.5" fill="#e08f78" opacity=".35" />
          {/* mouth */}
          <ellipse className="mouth" cx="60" cy="74" rx="5.5" ry="1.6" fill="#7a3b33" />
          {/* headset */}
          <path d="M37 60a23 25 0 0 1 46 0" fill="none" stroke="#111827" strokeWidth="3" />
          <rect x="33" y="56" width="7" height="12" rx="3" fill="#111827" />
          <path d="M37 68q2 10 16 8" fill="none" stroke="#111827" strokeWidth="2" strokeLinecap="round" />
          <circle cx="54" cy="76" r="2" fill="#5eead4" />
        </g>
      </svg>
      <span className="status-dot" />
    </div>
  );
}
