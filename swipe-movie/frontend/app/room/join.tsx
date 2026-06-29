import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { PrimaryButton } from "@/src/components";
import { C, F, RAD, SP } from "@/src/theme";

export default function JoinRoom() {
  const insets = useSafeAreaInsets();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const join = async () => {
    setError("");
    setBusy(true);
    try {
      const room = await api.post("/rooms/join", { join_code: code.trim().toUpperCase() });
      router.replace(`/room/${room.id}` as any);
    } catch (e: any) {
      setError(e.message || "Could not join");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + SP.md }]}>
      <Pressable testID="join-back" onPress={() => router.back()} style={{ marginBottom: SP.lg }}>
        <Ionicons name="chevron-back" size={26} color={C.onSurface} />
      </Pressable>
      <Text style={styles.h1}>Join a room</Text>
      <Text style={styles.sub}>Enter the 6-character invite code.</Text>

      <TextInput
        testID="join-code-input"
        style={styles.input}
        placeholder="ABC123"
        placeholderTextColor={C.zinc}
        autoCapitalize="characters"
        maxLength={6}
        value={code}
        onChangeText={setCode}
      />
      {error ? <Text style={styles.error} testID="join-error">{error}</Text> : null}
      <PrimaryButton title={busy ? "Joining…" : "Join room"} onPress={join} disabled={busy || code.length < 4} testID="confirm-join-room" style={{ marginTop: SP.xl }} />

      <Text style={styles.hint}>Try demo code: MOVIE1</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface, paddingHorizontal: SP.lg },
  h1: { fontFamily: F.display, fontSize: 26, color: C.onSurface },
  sub: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, marginTop: SP.xs, marginBottom: SP.xl },
  input: { height: 64, borderRadius: RAD.md, backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, color: C.onSurface, fontFamily: F.display, fontSize: 28, textAlign: "center", letterSpacing: 8 },
  error: { color: C.error, fontFamily: F.body, marginTop: SP.md },
  hint: { fontFamily: F.body, fontSize: 12, color: C.zinc, textAlign: "center", marginTop: SP.xl },
});
