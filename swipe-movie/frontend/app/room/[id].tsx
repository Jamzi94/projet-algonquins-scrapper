import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, wsUrl } from "@/src/api";
import { GhostButton, GlassView, Loader, MatchBadge, PrimaryButton, SwipeDeck, T } from "@/src/components";
import { C, F, RAD, SP } from "@/src/theme";

const DIR_VOTE: any = { right: "like", left: "dislike", up: "superlike", down: "veto", tap: "neutral" };

export default function RoomScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const [room, setRoom] = useState<any>(null);
  const [candidates, setCandidates] = useState<any[]>([]);
  const [result, setResult] = useState<any>(null);
  const [view, setView] = useState<"lobby" | "vote" | "result">("lobby");
  const [me, setMe] = useState<any>(null);
  const ws = useRef<WebSocket | null>(null);

  const loadRoom = useCallback(async () => {
    const r = await api.get(`/rooms/${id}`);
    setRoom(r);
    if (r.status === "voting" && view === "lobby") setView("vote");
    if (r.status === "decided") setView("result");
    return r;
  }, [id, view]);

  const loadCandidates = useCallback(async () => {
    const d = await api.get(`/rooms/${id}/candidates`);
    setCandidates(d.results);
  }, [id]);

  const loadResult = useCallback(async () => {
    const d = await api.get(`/rooms/${id}/result`);
    setResult(d);
    if (d.winner) setView("result");
  }, [id]);

  useEffect(() => {
    api.get("/auth/me").then(setMe).catch(() => {});
    loadRoom();
    try {
      ws.current = new WebSocket(wsUrl(id as string));
      ws.current.onmessage = () => {
        loadRoom();
        loadResult();
      };
    } catch {}
    return () => ws.current?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (view === "vote") {
      loadCandidates();
      loadResult();
    }
  }, [view, loadCandidates, loadResult]);

  if (!room) return <Loader label="Loading room…" />;
  const isOwner = me && room.owner_id === me.id;

  const start = async () => {
    await api.post(`/rooms/${id}/start`);
    await loadRoom();
    setView("vote");
  };

  const vote = async (card: any, dir: string) => {
    const v = DIR_VOTE[dir];
    try {
      const summary = await api.post(`/rooms/${id}/vote`, { content_id: card.content.id, vote: v });
      setResult(summary);
      if (summary.winner) setView("result");
    } catch {}
  };

  const relaunch = async (lowerThreshold?: boolean) => {
    await api.post(`/rooms/${id}/relaunch`, lowerThreshold ? { threshold_percent: Math.max(30, room.threshold_percent - 10) } : {});
    await loadRoom();
    setResult(null);
    setView("vote");
  };

  // ---- LOBBY ----
  if (view === "lobby") {
    return (
      <View style={[styles.root, { paddingTop: insets.top + SP.md }]}>
        <Header title={room.name} onBack={() => router.back()} />
        <ScrollView contentContainerStyle={{ padding: SP.lg }}>
          <View style={styles.codeBox}>
            <Text style={styles.codeLabel}>INVITE CODE</Text>
            <Text style={styles.code} testID="room-code">{room.join_code}</Text>
            <Text style={styles.codeHint}>Share this code — up to {room.max_users} players.</Text>
          </View>

          <Text style={styles.sectionHead}>Members ({room.members.length}/{room.max_users})</Text>
          {room.members.map((m: any) => (
            <View key={m.user_id} style={styles.memberRow}>
              <View style={styles.avatar}><Text style={styles.avatarText}>{(m.display_name || "?")[0].toUpperCase()}</Text></View>
              <Text style={styles.memberName}>{m.display_name}</Text>
              {m.role === "owner" ? <Text style={styles.ownerTag}>owner</Text> : null}
            </View>
          ))}

          <View style={styles.settingsBox}>
            <Text style={styles.settingText}>Threshold: {room.threshold_percent}% · Quorum: {room.quorum}</Text>
          </View>
        </ScrollView>
        <View style={[styles.footer, { paddingBottom: insets.bottom + SP.md }]}>
          {isOwner ? (
            <PrimaryButton title="Start swiping" icon="play" onPress={start} testID="start-room-btn" />
          ) : (
            <GhostButton title="Waiting for owner to start…" onPress={() => loadRoom()} testID="refresh-room-btn" />
          )}
        </View>
      </View>
    );
  }

  // ---- RESULT ----
  if (view === "result") {
    const w = result?.winner;
    return (
      <View style={[styles.root, { paddingTop: insets.top + SP.md }]}>
        <Header title="Result" onBack={() => router.back()} />
        <ScrollView contentContainerStyle={{ padding: SP.lg, paddingBottom: 120 }}>
          {w ? (
            <View testID="room-winner">
              <Text style={styles.winnerLabel}>🎉 Tonight you&apos;re watching</Text>
              <Pressable onPress={() => router.push(`/content/${w.content.id}` as any)} style={styles.winnerCard}>
                <Image source={{ uri: w.content.backdrop_url }} style={StyleSheet.absoluteFill} contentFit="cover" />
                <LinearGradient colors={["transparent", C.surface]} style={StyleSheet.absoluteFill} />
                <View style={styles.winnerInfo}>
                  <Text style={styles.winnerTitle}>{w.content.title}</Text>
                  <Text style={T.body}>{w.content.year} · {w.agreement_rate * 100}% agreement</Text>
                </View>
              </Pressable>
              <View style={styles.voteSummary}>
                <Summary label="Superlikes" value={w.superlikes} />
                <Summary label="Likes" value={w.likes} />
                <Summary label="Dislikes" value={w.dislikes} />
                <Summary label="Votes" value={w.total_votes} />
              </View>
              <PrimaryButton title="Open details" onPress={() => router.push(`/content/${w.content.id}` as any)} testID="open-winner" style={{ marginTop: SP.lg }} />
            </View>
          ) : (
            <View>
              <Text style={styles.winnerLabel}>No winner yet — top candidates</Text>
              {(result?.top_candidates || []).map((t: any) => (
                t.content ? (
                  <View key={t.content_id} style={styles.candRow} testID={`top-cand-${t.content_id}`}>
                    <Image source={{ uri: t.content.poster_url }} style={styles.candPoster} contentFit="cover" />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.candTitle}>{t.content.title}</Text>
                      <Text style={T.small}>{Math.round(t.agreement_rate * 100)}% agreement · {t.total_votes} votes · {t.vetoes} veto</Text>
                    </View>
                  </View>
                ) : null
              ))}
            </View>
          )}

          <Text style={styles.sectionHead}>Not happy?</Text>
          <View style={{ gap: SP.sm }}>
            <GhostButton title="Relaunch round" icon="refresh" onPress={() => relaunch(false)} testID="relaunch-btn" />
            {isOwner ? <GhostButton title="Lower threshold & relaunch" icon="trending-down" onPress={() => relaunch(true)} testID="lower-threshold-btn" /> : null}
          </View>
        </ScrollView>
      </View>
    );
  }

  // ---- VOTE ----
  const voted = result ? (result.winner ? 1 : 0) : 0;
  return (
    <View style={[styles.root, { paddingTop: insets.top + SP.md }]}>
      <View style={styles.voteHeader}>
        <Pressable testID="vote-back" onPress={() => router.back()}><Ionicons name="chevron-back" size={26} color={C.onSurface} /></Pressable>
        <GlassView style={styles.progressPill} intensity={30}>
          <Text style={styles.progressText}>Threshold {room.threshold_percent}% · Quorum {room.quorum}</Text>
        </GlassView>
        <Pressable testID="view-result-btn" onPress={() => { loadResult(); setView("result"); }}>
          <Ionicons name="trophy-outline" size={24} color={C.warning} />
        </Pressable>
      </View>

      <View style={{ flex: 1, paddingHorizontal: SP.xl }}>
        <SwipeDeck
          cards={candidates}
          onSwipe={vote}
          emptyLabel="All voted! Check the result."
          renderOverlay={(item) => (
            <View>
              <Text style={styles.cardTitle} numberOfLines={2}>{item.content.title}</Text>
              <Text style={[T.body, { marginTop: SP.xs }]}>
                {item.content.year} · {item.content.runtime}m · {(item.content.providers || []).slice(0, 2).join(", ")}
              </Text>
              {item.reasons?.[0] ? <Text style={styles.cardReason}>{item.reasons[0].text}</Text> : null}
            </View>
          )}
        />
      </View>
    </View>
  );
}

function Header({ title, onBack }: any) {
  return (
    <View style={styles.header}>
      <Pressable testID="header-back" onPress={onBack}><Ionicons name="chevron-back" size={26} color={C.onSurface} /></Pressable>
      <Text style={styles.headerTitle} numberOfLines={1}>{title}</Text>
      <View style={{ width: 26 }} />
    </View>
  );
}

function Summary({ label, value }: any) {
  return (
    <View style={styles.sumItem}>
      <Text style={styles.sumValue}>{value}</Text>
      <Text style={styles.sumLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: SP.lg, marginBottom: SP.sm },
  headerTitle: { fontFamily: F.display, fontSize: 20, color: C.onSurface, flex: 1, textAlign: "center" },
  codeBox: { backgroundColor: C.surface2, borderRadius: RAD.lg, padding: SP.xl, alignItems: "center", borderWidth: 1, borderColor: C.border },
  codeLabel: { fontFamily: F.medium, fontSize: 12, color: C.zinc, letterSpacing: 1 },
  code: { fontFamily: F.display, fontSize: 40, color: C.brand, letterSpacing: 6, marginTop: SP.sm },
  codeHint: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, marginTop: SP.sm },
  sectionHead: { fontFamily: F.display, fontSize: 18, color: C.onSurface, marginTop: SP.xl, marginBottom: SP.md },
  memberRow: { flexDirection: "row", alignItems: "center", gap: SP.md, paddingVertical: SP.sm },
  avatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: C.brandTint, alignItems: "center", justifyContent: "center" },
  avatarText: { fontFamily: F.medium, fontSize: 16, color: C.onBrandTint },
  memberName: { fontFamily: F.medium, fontSize: 15, color: C.onSurface, flex: 1 },
  ownerTag: { fontFamily: F.body, fontSize: 11, color: C.warning, textTransform: "uppercase" },
  settingsBox: { marginTop: SP.lg, padding: SP.md, borderRadius: RAD.md, backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border },
  settingText: { fontFamily: F.body, fontSize: 13, color: C.onSurface2 },
  footer: { padding: SP.lg, borderTopWidth: 1, borderTopColor: C.border },
  voteHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: SP.lg, marginBottom: SP.sm },
  progressPill: { paddingHorizontal: SP.md, paddingVertical: SP.xs, borderRadius: RAD.pill, borderWidth: 1, borderColor: C.border },
  progressText: { fontFamily: F.medium, fontSize: 12, color: C.onSurface },
  cardTitle: { fontFamily: F.display, fontSize: 28, color: C.onSurface },
  cardReason: { fontFamily: F.body, fontSize: 13, color: C.onBrandTint, marginTop: SP.sm },
  winnerLabel: { fontFamily: F.display, fontSize: 22, color: C.onSurface, marginBottom: SP.md, textAlign: "center" },
  winnerCard: { height: 220, borderRadius: RAD.lg, overflow: "hidden", justifyContent: "flex-end", backgroundColor: C.surface2 },
  winnerInfo: { padding: SP.lg },
  winnerTitle: { fontFamily: F.display, fontSize: 26, color: C.onSurface },
  voteSummary: { flexDirection: "row", justifyContent: "space-around", marginTop: SP.lg },
  sumItem: { alignItems: "center" },
  sumValue: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  sumLabel: { fontFamily: F.body, fontSize: 11, color: C.onSurface2, marginTop: 2 },
  candRow: { flexDirection: "row", alignItems: "center", gap: SP.md, backgroundColor: C.surface2, borderRadius: RAD.md, padding: SP.md, marginBottom: SP.sm, borderWidth: 1, borderColor: C.border },
  candPoster: { width: 44, height: 66, borderRadius: RAD.sm, backgroundColor: C.surface3 },
  candTitle: { fontFamily: F.medium, fontSize: 15, color: C.onSurface },
});
