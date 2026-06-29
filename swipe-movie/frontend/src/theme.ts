// SwipeNight design tokens — "6 Glass / Luxe DARK". NO BLUE. Font weights capped at 500.
export const C = {
  surface: "#050507",
  onSurface: "#F3F3F4",
  surface2: "#141417",
  onSurface2: "#A1A1AA",
  surface3: "#222227",
  onSurface3: "#D4D4D8",
  brand: "#E11D48",
  brand2: "#BE123C",
  brandTint: "#4C0519",
  onBrandTint: "#FDA4AF",
  onBrand: "#FFFFFF",
  success: "#10B981",
  warning: "#F59E0B",
  error: "#EF4444",
  zinc: "#52525B",
  border: "#27272A",
  borderStrong: "#3F3F46",
  divider: "#1F1F22",
  glass: "rgba(20,20,23,0.78)",
};

export const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const RAD = { sm: 6, md: 12, lg: 20, pill: 999 };

// Fraunces (display) and Satoshi (text). Capped at Medium (500).
export const F = {
  display: "Fraunces-Medium",
  displayReg: "Fraunces",
  medium: "Satoshi-Medium",
  body: "Satoshi",
};

export const FONT_FILES = {
  Fraunces: require("../assets/fonts/Fraunces-Regular.ttf"),
  "Fraunces-Medium": require("../assets/fonts/Fraunces-Medium.ttf"),
  "Fraunces-SemiBold": require("../assets/fonts/Fraunces-SemiBold.ttf"),
  Satoshi: require("../assets/fonts/Satoshi-Regular.ttf"),
  "Satoshi-Medium": require("../assets/fonts/Satoshi-Medium.ttf"),
};

export const PLATFORMS = ["Netflix", "Disney+", "Prime Video", "Apple TV+", "Max", "Crunchyroll", "Stremio", "Other"];
export const FORMATS = ["movies", "series", "anime"];
export const GENRES = ["Action", "Romance", "Comedy", "Drama", "Thriller", "Horror", "Sci-Fi", "Fantasy", "Documentary", "Animation", "Crime", "Adventure"];
export const MOODS = ["light", "dark", "funny", "emotional", "intense", "short", "long", "family", "solo", "group"];
export const COUNTRIES = ["US", "UK", "CA", "FR", "DE", "JP", "IN", "BR", "AU", "ES"];
export const REACTIONS = ["loved", "funny", "sad", "intense", "surprising", "slow", "disappointing", "masterpiece", "not_for_me"];
