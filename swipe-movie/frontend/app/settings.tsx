import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { GhostButton } from "@/src/components";
import { C, F, RAD, SP } from "@/src/theme";

const VIS = ["private", "friends", "public"];

export default function Settings() {
  const insets = useSafeAreaInsets();
  const { logout } = useAuth();
  const [privacy, setPrivacy] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);

  useEffect(() => {
    api.get("/users/me/privacy").then(setPrivacy).catch(() => {});
    api.get("/provider-status").then(setStatus).catch(() => {});
  }, []);

  const update = async (key: string, value: string) => {
    const next = { ...privacy, [key]: value };
    setPrivacy(next);
    await api.put("/users/me/privacy", { [key]: value });
  };

  const cycle = (key: string) => {
    const cur = privacy?.[key] || "private";
    const i = VIS.indexOf(cur);
    update(key, VIS[(i + 1) % VIS.length]);
  };

  const PrivacyRow = ({ label, k }: any) => (
    <Pressable testID={`privacy-${k}`} style={styles.row} onPress={() => cycle(k)}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.pill}>
        <Text style={styles.pillText}>{privacy?.[k] || "private"}</Text>
        <Ionicons name="swap-horizontal" size={14} color={C.onSurface2} />
      </View>
    </Pressable>
  );

  const dangerHistory = async () => {
    await api.del("/users/me/history");
  };
  const dangerAccount = async () => {
    await api.del("/users/me");
    await logout();
    router.replace("/" as any);
  };

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ paddingTop: insets.top + SP.md, paddingBottom: 60, paddingHorizontal: SP.lg }}>
      <View style={styles.header}>
        <Pressable testID="settings-back" onPress={() => router.back()}><Ionicons name="chevron-back" size={26} color={C.onSurface} /></Pressable>
        <Text style={styles.title}>Privacy &amp; Settings</Text>
        <View style={{ width: 26 }} />
      </View>

      <Text style={styles.section}>Visibility</Text>
      <Text style={styles.note}>Everything is private by default. Tap to cycle through private → friends → public.</Text>
      <PrivacyRow label="Viewing history" k="history_visibility" />
      <PrivacyRow label="Ratings" k="ratings_visibility" />
      <PrivacyRow label="Watchlist" k="watchlist_visibility" />
      <PrivacyRow label="Profile" k="profile_visibility" />

      <Text style={styles.section}>Data &amp; account</Text>
      <View style={{ gap: SP.sm }}>
        <GhostButton title="Delete my history" icon="trash-outline" onPress={dangerHistory} testID="delete-history-btn" />
        <Pressable testID="delete-account-btn" style={styles.danger} onPress={dangerAccount}>
          <Ionicons name="warning-outline" size={18} color={C.error} />
          <Text style={styles.dangerText}>Delete my account</Text>
        </Pressable>
      </View>

      <Text style={styles.section}>Credits &amp; data sources</Text>
      <View style={styles.creditCard} testID="credits-card">
        <Text style={styles.creditText}>
          This product uses the TMDB API but is not endorsed or certified by TMDB.
        </Text>
        <Text style={[styles.creditText, { marginTop: SP.sm }]}>
          CineFeel is currently a free, non-commercial beta. Movie, series and anime
          metadata may be provided by The Movie Database (TMDB); when external data is
          unavailable the app uses its built-in seed catalog.
        </Text>
      </View>

      <Text style={styles.section}>Developer status</Text>
      <View style={styles.devCard} testID="dev-status-card">
        <DevRow label="TMDB enabled" value={status?.tmdb_enabled} />
        <DevRow label="External APIs enabled" value={status?.external_apis_enabled} />
        <DevRow label="Commercial mode" value={status?.commercial_mode} />
        <DevRow label="Seed catalog fallback" value={status?.seed_catalog_fallback} />
        {status?.reason ? <Text style={styles.devReason}>{status.reason}</Text> : null}
      </View>

      <Text style={styles.note}>CineFeel never exposes your viewing history without your consent. Rooms expire automatically after use.</Text>
    </ScrollView>
  );
}

function DevRow({ label, value }: { label: string; value?: boolean }) {
  return (
    <View style={styles.devRow}>
      <Text style={styles.devLabel}>{label}</Text>
      <View style={[styles.devBadge, { backgroundColor: value ? C.brandTint : C.surface3 }]}>
        <Text style={[styles.devBadgeText, { color: value ? C.onBrandTint : C.onSurface2 }]}>
          {value ? "yes" : "no"}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: SP.lg },
  title: { fontFamily: F.display, fontSize: 20, color: C.onSurface },
  section: { fontFamily: F.display, fontSize: 18, color: C.onSurface, marginTop: SP.xl, marginBottom: SP.sm },
  note: { fontFamily: F.body, fontSize: 12, color: C.zinc, marginBottom: SP.md, lineHeight: 18 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: C.surface2, borderRadius: RAD.md, borderWidth: 1, borderColor: C.border, padding: SP.lg, marginBottom: SP.sm },
  rowLabel: { fontFamily: F.medium, fontSize: 15, color: C.onSurface },
  pill: { flexDirection: "row", alignItems: "center", gap: SP.sm, backgroundColor: C.surface3, borderRadius: RAD.pill, paddingHorizontal: SP.md, paddingVertical: SP.xs },
  pillText: { fontFamily: F.medium, fontSize: 12, color: C.onSurface, textTransform: "capitalize" },
  danger: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: SP.sm, height: 52, borderRadius: RAD.md, borderWidth: 1, borderColor: C.error },
  dangerText: { fontFamily: F.medium, fontSize: 16, color: C.error },
  creditCard: { backgroundColor: C.surface2, borderRadius: RAD.md, borderWidth: 1, borderColor: C.border, padding: SP.lg },
  creditText: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, lineHeight: 19 },
  devCard: { backgroundColor: C.surface2, borderRadius: RAD.md, borderWidth: 1, borderColor: C.border, padding: SP.lg, gap: SP.sm },
  devRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  devLabel: { fontFamily: F.body, fontSize: 14, color: C.onSurface },
  devBadge: { borderRadius: RAD.pill, paddingHorizontal: SP.md, paddingVertical: 2 },
  devBadgeText: { fontFamily: F.medium, fontSize: 12 },
  devReason: { fontFamily: F.body, fontSize: 12, color: C.warning, marginTop: SP.xs },
});
