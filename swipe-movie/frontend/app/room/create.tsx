import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { Chip, PrimaryButton } from "@/src/components";
import { C, F, GENRES, PLATFORMS, RAD, SP } from "@/src/theme";

function toggle(a: string[], v: string) {
  return a.includes(v) ? a.filter((x) => x !== v) : [...a, v];
}

export default function CreateRoom() {
  const insets = useSafeAreaInsets();
  const [name, setName] = useState("");
  const [threshold, setThreshold] = useState(60);
  const [quorum, setQuorum] = useState(2);
  const [formats, setFormats] = useState<string[]>([]);
  const [genres, setGenres] = useState<string[]>([]);
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [allowSeenSome, setAllowSeenSome] = useState(true);
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    try {
      const room = await api.post("/rooms", {
        name: name || "Movie Night",
        threshold_percent: threshold,
        quorum,
        max_users: 5,
        filters: { formats, genres, platforms, allow_seen_by_some: allowSeenSome, allow_seen_by_all: false, languages: [] },
      });
      router.replace(`/room/${room.id}` as any);
    } finally {
      setBusy(false);
    }
  };

  const Stepper = ({ label, value, setValue, min, max, step, suffix }: any) => (
    <View style={styles.stepper}>
      <Text style={styles.stepLabel}>{label}</Text>
      <View style={styles.stepCtrl}>
        <Pressable testID={`${label}-minus`} style={styles.stepBtn} onPress={() => setValue(Math.max(min, value - step))}>
          <Ionicons name="remove" size={20} color={C.onSurface} />
        </Pressable>
        <Text style={styles.stepValue}>{value}{suffix}</Text>
        <Pressable testID={`${label}-plus`} style={styles.stepBtn} onPress={() => setValue(Math.min(max, value + step))}>
          <Ionicons name="add" size={20} color={C.onSurface} />
        </Pressable>
      </View>
    </View>
  );

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ padding: SP.lg, paddingTop: insets.top + SP.md, paddingBottom: 120 }} showsVerticalScrollIndicator={false}>
        <Pressable testID="create-back" onPress={() => router.back()} style={{ marginBottom: SP.md }}>
          <Ionicons name="chevron-back" size={26} color={C.onSurface} />
        </Pressable>
        <Text style={styles.h1}>Create a room</Text>

        <Text style={styles.label}>Room name</Text>
        <TextInput testID="room-name-input" style={styles.input} placeholder="Friday Movie Night" placeholderTextColor={C.zinc} value={name} onChangeText={setName} />

        <Stepper label="Agreement threshold" value={threshold} setValue={setThreshold} min={30} max={100} step={5} suffix="%" />
        <Stepper label="Quorum (min voters)" value={quorum} setValue={setQuorum} min={1} max={5} step={1} suffix="" />

        <Text style={styles.label}>Formats</Text>
        <View style={styles.chipWrap}>
          {["movie", "series", "anime"].map((f) => (
            <Chip key={f} label={f} active={formats.includes(f)} onPress={() => setFormats(toggle(formats, f))} testID={`rf-format-${f}`} />
          ))}
        </View>

        <Text style={styles.label}>Genres</Text>
        <View style={styles.chipWrap}>
          {GENRES.map((g) => (
            <Chip key={g} label={g} active={genres.includes(g)} onPress={() => setGenres(toggle(genres, g))} testID={`rf-genre-${g}`} />
          ))}
        </View>

        <Text style={styles.label}>Platforms</Text>
        <View style={styles.chipWrap}>
          {PLATFORMS.slice(0, 6).map((p) => (
            <Chip key={p} label={p} active={platforms.includes(p)} onPress={() => setPlatforms(toggle(platforms, p))} testID={`rf-platform-${p}`} />
          ))}
        </View>

        <Pressable testID="allow-seen-some" style={styles.toggle} onPress={() => setAllowSeenSome(!allowSeenSome)}>
          <Ionicons name={allowSeenSome ? "checkbox" : "square-outline"} size={20} color={allowSeenSome ? C.brand : C.onSurface2} />
          <Text style={styles.toggleText}>Allow titles already seen by some members</Text>
        </Pressable>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + SP.md }]}>
        <PrimaryButton title={busy ? "Creating…" : "Create room"} onPress={create} disabled={busy} testID="confirm-create-room" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  h1: { fontFamily: F.display, fontSize: 26, color: C.onSurface, marginBottom: SP.md },
  label: { fontFamily: F.medium, fontSize: 14, color: C.onSurface2, marginTop: SP.lg, marginBottom: SP.sm },
  input: { height: 52, borderRadius: RAD.md, backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, paddingHorizontal: SP.lg, color: C.onSurface, fontFamily: F.body, fontSize: 16 },
  stepper: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: SP.lg },
  stepLabel: { fontFamily: F.medium, fontSize: 15, color: C.onSurface, flex: 1 },
  stepCtrl: { flexDirection: "row", alignItems: "center", gap: SP.md },
  stepBtn: { width: 38, height: 38, borderRadius: 19, backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, alignItems: "center", justifyContent: "center" },
  stepValue: { fontFamily: F.medium, fontSize: 16, color: C.onSurface, minWidth: 48, textAlign: "center" },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: SP.sm },
  toggle: { flexDirection: "row", alignItems: "center", gap: SP.sm, marginTop: SP.xl },
  toggleText: { fontFamily: F.body, fontSize: 14, color: C.onSurface, flex: 1 },
  footer: { position: "absolute", bottom: 0, left: 0, right: 0, padding: SP.lg, backgroundColor: C.surface, borderTopWidth: 1, borderTopColor: C.border },
});
