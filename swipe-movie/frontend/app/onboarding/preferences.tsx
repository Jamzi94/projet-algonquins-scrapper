import { router } from "expo-router";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Chip, PrimaryButton } from "@/src/components";
import { C, COUNTRIES, F, GENRES, MOODS, PLATFORMS, RAD, SP } from "@/src/theme";

function toggle(arr: string[], v: string) {
  return arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
}

export default function Preferences() {
  const insets = useSafeAreaInsets();
  const { user, setUser } = useAuth();
  const [country, setCountry] = useState(user?.preferences?.country || "US");
  const [platforms, setPlatforms] = useState<string[]>(user?.preferences?.platforms || []);
  const [formats, setFormats] = useState<string[]>(user?.preferences?.formats || ["movies", "series"]);
  const [genres, setGenres] = useState<string[]>(user?.preferences?.genres || []);
  const [moods, setMoods] = useState<string[]>(user?.preferences?.moods || []);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const u = await api.put("/users/preferences", { country, platforms, formats, genres, moods });
      setUser(u);
      router.push("/onboarding/calibration" as any);
    } finally {
      setSaving(false);
    }
  };

  const Section = ({ title, children }: any) => (
    <View style={{ marginBottom: SP.xl }}>
      <Text style={styles.section}>{title}</Text>
      <View style={styles.chipWrap}>{children}</View>
    </View>
  );

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={{ padding: SP.xl, paddingTop: insets.top + SP.lg, paddingBottom: 120 }}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.h1}>Let&apos;s tune your taste</Text>
        <Text style={styles.sub}>This powers your recommendations. You can change it anytime.</Text>

        <Section title="Region">
          {COUNTRIES.map((c) => (
            <Chip key={c} label={c} active={country === c} onPress={() => setCountry(c)} testID={`country-${c}`} />
          ))}
        </Section>

        <Section title="Streaming platforms you own">
          {PLATFORMS.map((p) => (
            <Chip key={p} label={p} active={platforms.includes(p)} onPress={() => setPlatforms(toggle(platforms, p))} testID={`platform-${p}`} />
          ))}
        </Section>

        <Section title="Formats you watch">
          {["movies", "series", "anime"].map((f) => (
            <Chip key={f} label={f} active={formats.includes(f)} onPress={() => setFormats(toggle(formats, f))} testID={`format-${f}`} />
          ))}
        </Section>

        <Section title="Favourite genres">
          {GENRES.map((g) => (
            <Chip key={g} label={g} active={genres.includes(g)} onPress={() => setGenres(toggle(genres, g))} testID={`genre-${g}`} />
          ))}
        </Section>

        <Section title="Mood preferences">
          {MOODS.map((m) => (
            <Chip key={m} label={m} active={moods.includes(m)} onPress={() => setMoods(toggle(moods, m))} testID={`mood-${m}`} />
          ))}
        </Section>

        <View style={styles.infoCard}>
          <Text style={styles.infoTitle}>Connect Trakt (optional)</Text>
          <Text style={styles.infoText}>Coming soon — sync your watch history from Trakt to supercharge recommendations.</Text>
        </View>
        <View style={styles.infoCard}>
          <Text style={styles.infoTitle}>Import history (optional)</Text>
          <Text style={styles.infoText}>Manual import guides for Netflix, Disney+ &amp; Prime Video are on the way.</Text>
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + SP.md }]}>
        <PrimaryButton
          title={saving ? "Saving…" : "Continue to calibration"}
          onPress={save}
          disabled={saving || genres.length === 0}
          testID="preferences-continue"
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  h1: { fontFamily: F.display, fontSize: 28, color: C.onSurface },
  sub: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, marginTop: SP.xs, marginBottom: SP.xl },
  section: { fontFamily: F.medium, fontSize: 16, color: C.onSurface, marginBottom: SP.md },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: SP.sm },
  infoCard: { padding: SP.lg, borderRadius: RAD.md, backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, marginBottom: SP.md },
  infoTitle: { fontFamily: F.medium, fontSize: 15, color: C.onSurface },
  infoText: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, marginTop: SP.xs },
  footer: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    padding: SP.lg,
    backgroundColor: C.surface,
    borderTopWidth: 1,
    borderTopColor: C.border,
  },
});
