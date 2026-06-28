import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { EmptyState, GhostButton, Loader, PrimaryButton } from "@/src/components";
import { C, F, RAD, SP } from "@/src/theme";

export default function Rooms() {
  const insets = useSafeAreaInsets();
  const [rooms, setRooms] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const d = await api.get("/rooms");
      setRooms(d.results);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + SP.sm }]}>
        <Text style={styles.title}>Rooms</Text>
        <Text style={styles.sub}>Swipe together. Decide faster.</Text>
      </View>

      <View style={styles.actions}>
        <PrimaryButton title="Create room" icon="add" onPress={() => router.push("/room/create" as any)} testID="create-room-btn" style={{ flex: 1 }} />
        <GhostButton title="Join" icon="enter-outline" onPress={() => router.push("/room/join" as any)} testID="join-room-btn" style={{ flex: 1 }} />
      </View>

      {loading ? (
        <Loader />
      ) : rooms.length === 0 ? (
        <EmptyState icon="people-outline" title="No rooms yet" subtitle="Create a room and invite up to 5 friends." testID="rooms-empty" />
      ) : (
        <ScrollView contentContainerStyle={{ padding: SP.lg, paddingBottom: 110, gap: SP.md }} showsVerticalScrollIndicator={false}>
          {rooms.map((r) => (
            <Pressable key={r.id} testID={`room-card-${r.id}`} style={styles.card} onPress={() => router.push(`/room/${r.id}` as any)}>
              <View style={{ flex: 1 }}>
                <Text style={styles.roomName}>{r.name}</Text>
                <Text style={styles.roomMeta}>
                  {r.members.length}/{r.max_users} members · code {r.join_code} · {r.status}
                </Text>
                <View style={styles.avatars}>
                  {r.members.slice(0, 5).map((m: any, i: number) => (
                    <View key={m.user_id} style={[styles.avatar, { marginLeft: i === 0 ? 0 : -10 }]}>
                      <Text style={styles.avatarText}>{(m.display_name || "?")[0].toUpperCase()}</Text>
                    </View>
                  ))}
                </View>
              </View>
              <Ionicons name="chevron-forward" size={22} color={C.zinc} />
            </Pressable>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { paddingHorizontal: SP.lg },
  title: { fontFamily: F.display, fontSize: 26, color: C.onSurface },
  sub: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, marginTop: SP.xs },
  actions: { flexDirection: "row", gap: SP.md, paddingHorizontal: SP.lg, marginTop: SP.lg },
  card: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: C.surface2,
    borderRadius: RAD.md,
    borderWidth: 1,
    borderColor: C.border,
    padding: SP.lg,
  },
  roomName: { fontFamily: F.medium, fontSize: 17, color: C.onSurface },
  roomMeta: { fontFamily: F.body, fontSize: 12, color: C.onSurface2, marginTop: SP.xs, textTransform: "capitalize" },
  avatars: { flexDirection: "row", marginTop: SP.md },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: C.brandTint,
    borderWidth: 1,
    borderColor: C.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { fontFamily: F.medium, fontSize: 13, color: C.onBrandTint },
});
