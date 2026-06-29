import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { GhostButton, Loader } from "@/src/components";
import { C, F, RAD, SP } from "@/src/theme";

export default function Profile() {
  const insets = useSafeAreaInsets();
  const { user, logout } = useAuth();
  const [profile, setProfile] = useState<any>(null);

  useFocusEffect(
    useCallback(() => {
      api.get("/users/me/profile").then(setProfile).catch(() => {});
    }, [])
  );

  if (!profile) return <Loader />;
  const sc = profile.state_counts || {};

  const Stat = ({ label, value }: any) => (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );

  const Row = ({ icon, label, onPress, danger, testID }: any) => (
    <Pressable testID={testID} style={styles.row} onPress={onPress}>
      <Ionicons name={icon} size={20} color={danger ? C.error : C.onSurface2} />
      <Text style={[styles.rowText, danger && { color: C.error }]}>{label}</Text>
      <Ionicons name="chevron-forward" size={18} color={C.zinc} />
    </Pressable>
  );

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ paddingTop: insets.top + SP.lg, paddingBottom: 110 }} showsVerticalScrollIndicator={false}>
      <View style={styles.head}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{(user?.display_name || "?")[0].toUpperCase()}</Text>
        </View>
        <Text style={styles.name}>{user?.display_name}</Text>
        <Text style={styles.handle}>@{user?.username} · {user?.preferences?.country}</Text>
      </View>

      <View style={styles.stats}>
        <Stat label="Liked" value={sc.seen_liked || 0} />
        <Stat label="Watchlist" value={sc.watchlist || 0} />
        <Stat label="Rated" value={profile.total_rated || 0} />
        <Stat label="Reviews" value={profile.reviews || 0} />
      </View>

      <View style={styles.section}>
        <Row icon="options-outline" label="Edit preferences" onPress={() => router.push("/onboarding/preferences" as any)} testID="edit-prefs" />
        <Row icon="sparkles-outline" label="Re-run calibration" onPress={() => router.push("/onboarding/calibration" as any)} testID="recalibrate" />
        <Row icon="shield-checkmark-outline" label="Privacy & settings" onPress={() => router.push("/settings" as any)} testID="open-settings" />
      </View>

      <View style={{ paddingHorizontal: SP.lg, marginTop: SP.xl }}>
        <GhostButton title="Log out" icon="log-out-outline" onPress={async () => { await logout(); router.replace("/" as any); }} testID="logout-btn" />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  head: { alignItems: "center" },
  avatar: { width: 80, height: 80, borderRadius: 40, backgroundColor: C.brandTint, alignItems: "center", justifyContent: "center" },
  avatarText: { fontFamily: F.display, fontSize: 32, color: C.onBrandTint },
  name: { fontFamily: F.display, fontSize: 24, color: C.onSurface, marginTop: SP.md },
  handle: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, marginTop: SP.xs },
  stats: { flexDirection: "row", justifyContent: "space-around", marginTop: SP.xl, paddingHorizontal: SP.lg },
  stat: { alignItems: "center" },
  statValue: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  statLabel: { fontFamily: F.body, fontSize: 12, color: C.onSurface2, marginTop: SP.xs },
  section: { marginTop: SP.xxl, paddingHorizontal: SP.lg, gap: SP.sm },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: SP.md,
    backgroundColor: C.surface2,
    borderRadius: RAD.md,
    borderWidth: 1,
    borderColor: C.border,
    padding: SP.lg,
  },
  rowText: { flex: 1, fontFamily: F.medium, fontSize: 15, color: C.onSurface },
});
