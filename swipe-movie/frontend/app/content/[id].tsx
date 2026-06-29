import { Ionicons } from "@expo/vector-icons";
import BottomSheet, { BottomSheetBackdrop, BottomSheetScrollView } from "@gorhom/bottom-sheet";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { router, useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useCallback, useEffect, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { Chip, GlassView, Loader, MatchBadge, Stars, T } from "@/src/components";
import { C, F, RAD, REACTIONS, SP } from "@/src/theme";

const STATE_BTNS = [
  { key: "like", icon: "heart", label: "Liked", state: "seen_liked" },
  { key: "dislike", icon: "thumbs-down", label: "Disliked", state: "seen_disliked" },
  { key: "abandoned", icon: "exit-outline", label: "Abandoned", state: "abandoned" },
  { key: "neutral", icon: "remove-circle-outline", label: "Neutral", state: "seen_neutral" },
];

export default function ContentDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<any>(null);
  const sheetRef = useRef<BottomSheet>(null);

  // review form
  const [rating, setRating] = useState(0);
  const [reaction, setReaction] = useState("");
  const [body, setBody] = useState("");
  const [spoiler, setSpoiler] = useState(false);
  const [visibility, setVisibility] = useState("public");

  const load = useCallback(async () => {
    const d = await api.get(`/contents/${id}`);
    setData(d);
  }, [id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (!data) return <Loader />;
  const c = data.content;
  const us = data.user_state || {};

  const doEvent = async (type: string) => {
    await api.post("/events", { content_id: id, event_type: type });
    load();
  };
  const toggleWatchlist = async () => {
    if (us.state === "watchlist") await api.del(`/watchlist/${id}`);
    else await api.post(`/watchlist/${id}`);
    load();
  };
  const exclude = async () => {
    await api.put(`/contents/${id}/state`, { state: "excluded_from_recommendations", is_excluded_from_reco: true });
    load();
  };

  const submitReview = async () => {
    await api.post("/reviews", {
      content_id: id,
      rating: rating || null,
      reaction: reaction || null,
      body: body || null,
      is_spoiler: spoiler,
      visibility,
    });
    sheetRef.current?.close();
    setBody("");
    load();
  };

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: 130 }} showsVerticalScrollIndicator={false}>
        <View style={styles.backdrop}>
          <Image source={{ uri: c.backdrop_url }} style={StyleSheet.absoluteFill} contentFit="cover" transition={250} />
          <LinearGradient colors={["rgba(5,5,7,0.3)", "rgba(5,5,7,0.2)", C.surface]} style={StyleSheet.absoluteFill} />
          <Pressable testID="detail-back" onPress={() => router.back()} style={[styles.backBtn, { top: insets.top + SP.sm }]}>
            <Ionicons name="chevron-back" size={26} color={C.onSurface} />
          </Pressable>
          <View style={styles.posterFloat}>
            <Image source={{ uri: c.poster_url }} style={StyleSheet.absoluteFill} contentFit="cover" />
          </View>
        </View>

        <View style={styles.body}>
          <Text style={styles.title}>{c.title}</Text>
          {c.original_title && c.original_title !== c.title ? (
            <Text style={styles.original}>{c.original_title}</Text>
          ) : null}
          <View style={styles.metaRow}>
            <MatchBadge score={data.match_score} />
            <Text style={styles.meta}>{c.year} · {c.type} · {c.runtime}m</Text>
          </View>

          <View style={styles.genreRow}>
            {(c.genres || []).map((g: string) => (
              <View key={g} style={styles.genrePill}>
                <Text style={styles.genrePillText}>{g}</Text>
              </View>
            ))}
          </View>

          {/* Why recommended */}
          {data.reasons?.length ? (
            <View style={styles.reasonBox}>
              <Text style={styles.reasonHead}>Why this?</Text>
              {data.reasons.map((r: any, i: number) => (
                <Text key={i} style={styles.reasonText}>• {r.text}</Text>
              ))}
            </View>
          ) : null}

          <Text style={styles.overview}>{c.overview}</Text>

          {c.trailer_url ? (
            <Pressable testID="watch-trailer" style={styles.trailer} onPress={() => WebBrowser.openBrowserAsync(c.trailer_url)}>
              <Ionicons name="play-circle" size={20} color={C.onSurface} />
              <Text style={styles.trailerText}>Watch trailer</Text>
            </Pressable>
          ) : null}

          {/* Meta details */}
          <Detail label="Director / Creator" value={c.creator} />
          <Detail label="Studio" value={(c.studios || []).join(", ")} />
          <Detail label="Cast" value={(c.cast || []).join(", ")} />
          {c.type !== "movie" ? <Detail label="Seasons / Episodes" value={`${c.seasons} seasons · ${c.episodes} episodes`} /> : null}
          <Detail label="Available on" value={(c.providers || []).join(", ") || "Not on your platforms"} />
          <Detail label="Community rating" value={data.community_rating ? `${data.community_rating} ★ (${data.community_votes} votes)` : "No ratings yet"} />
          <Detail label="Data source" value={c.metadata_source === "tmdb" ? "TMDB" : "Seed catalog (offline)"} />

          {/* Your state actions */}
          <Text style={styles.sectionHead}>Mark this title</Text>
          <View style={styles.stateGrid}>
            {STATE_BTNS.map((b) => (
              <Pressable
                key={b.key}
                testID={`state-${b.key}`}
                style={[styles.stateBtn, us.state === b.state && styles.stateBtnActive]}
                onPress={() => doEvent(b.key)}
              >
                <Ionicons name={b.icon as any} size={20} color={us.state === b.state ? C.brand : C.onSurface2} />
                <Text style={[styles.stateLabel, us.state === b.state && { color: C.brand }]}>{b.label}</Text>
              </Pressable>
            ))}
            <Pressable testID="state-exclude" style={[styles.stateBtn, us.is_excluded_from_reco && styles.stateBtnActive]} onPress={exclude}>
              <Ionicons name="eye-off-outline" size={20} color={us.is_excluded_from_reco ? C.brand : C.onSurface2} />
              <Text style={[styles.stateLabel, us.is_excluded_from_reco && { color: C.brand }]}>Exclude</Text>
            </Pressable>
          </View>

          {/* Reviews */}
          <Text style={styles.sectionHead}>Reviews</Text>
          {data.reviews?.length ? (
            data.reviews.map((r: any) => (
              <View key={r.id} style={styles.review} testID={`review-${r.id}`}>
                <View style={styles.reviewHead}>
                  <Text style={styles.reviewAuthor}>{r.author}</Text>
                  {r.rating ? <Stars value={r.rating} size={13} /> : null}
                </View>
                {r.reaction ? <Text style={styles.reviewReaction}>{r.reaction.replace(/_/g, " ")}</Text> : null}
                {r.body ? (
                  <Text style={styles.reviewBody}>{r.is_spoiler ? "⚠️ Spoiler — " : ""}{r.body}</Text>
                ) : null}
              </View>
            ))
          ) : (
            <Text style={styles.noReviews}>No reviews yet. Be the first!</Text>
          )}
        </View>
      </ScrollView>

      {/* Floating action bar */}
      <GlassView style={[styles.actionBar, { paddingBottom: insets.bottom + SP.sm }]} intensity={50}>
        <Pressable testID="fab-watchlist" style={styles.fabSecondary} onPress={toggleWatchlist}>
          <Ionicons name={us.state === "watchlist" ? "bookmark" : "bookmark-outline"} size={22} color={us.state === "watchlist" ? C.brand : C.onSurface} />
          <Text style={styles.fabSecText}>{us.state === "watchlist" ? "Saved" : "Watchlist"}</Text>
        </Pressable>
        <Pressable
          testID="fab-rate-review"
          style={styles.fabPrimary}
          onPress={() => { setRating(us.rating || 0); sheetRef.current?.expand(); }}
        >
          <Ionicons name="star" size={18} color={C.onBrand} />
          <Text style={styles.fabPrimText}>Rate &amp; Review</Text>
        </Pressable>
      </GlassView>

      <BottomSheet
        ref={sheetRef}
        index={-1}
        snapPoints={["75%"]}
        enablePanDownToClose
        backgroundStyle={{ backgroundColor: C.surface2 }}
        handleIndicatorStyle={{ backgroundColor: C.borderStrong }}
        backdropComponent={(p) => <BottomSheetBackdrop {...p} disappearsOnIndex={-1} appearsOnIndex={0} />}
      >
        <BottomSheetScrollView contentContainerStyle={{ padding: SP.xl }}>
          <Text style={styles.sheetTitle}>Rate &amp; Review</Text>
          <Text style={styles.sheetLabel}>Your rating</Text>
          <View style={styles.starRow}>
            {[1, 2, 3, 4, 5].map((s) => (
              <Pressable key={s} testID={`rate-star-${s}`} onPress={() => setRating(s === rating ? s - 0.5 : s)}>
                <Ionicons name={rating >= s ? "star" : rating >= s - 0.5 ? "star-half" : "star-outline"} size={34} color={C.warning} />
              </Pressable>
            ))}
          </View>

          <Text style={styles.sheetLabel}>Reaction</Text>
          <View style={styles.chipWrap}>
            {REACTIONS.map((r) => (
              <Chip key={r} label={r.replace(/_/g, " ")} active={reaction === r} onPress={() => setReaction(r === reaction ? "" : r)} testID={`reaction-${r}`} />
            ))}
          </View>

          <Text style={styles.sheetLabel}>Review (optional)</Text>
          <TextInput
            testID="review-body-input"
            style={styles.reviewInput}
            placeholder="Share your thoughts…"
            placeholderTextColor={C.zinc}
            multiline
            value={body}
            onChangeText={setBody}
          />

          <View style={styles.toggleRow}>
            <Pressable testID="toggle-spoiler" style={styles.toggle} onPress={() => setSpoiler(!spoiler)}>
              <Ionicons name={spoiler ? "checkbox" : "square-outline"} size={20} color={spoiler ? C.brand : C.onSurface2} />
              <Text style={styles.toggleText}>Contains spoilers</Text>
            </Pressable>
          </View>

          <Text style={styles.sheetLabel}>Visibility</Text>
          <View style={styles.chipWrap}>
            {["private", "friends", "public"].map((v) => (
              <Chip key={v} label={v} active={visibility === v} onPress={() => setVisibility(v)} testID={`visibility-${v}`} />
            ))}
          </View>

          <Pressable testID="submit-review" style={styles.submit} onPress={submitReview}>
            <Text style={styles.submitText}>Submit</Text>
          </Pressable>
        </BottomSheetScrollView>
      </BottomSheet>
    </View>
  );
}

function Detail({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <View style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  backdrop: { height: 300 },
  backBtn: { position: "absolute", left: SP.md, width: 40, height: 40, borderRadius: 20, backgroundColor: "rgba(5,5,7,0.5)", alignItems: "center", justifyContent: "center" },
  posterFloat: { position: "absolute", bottom: -40, left: SP.lg, width: 96, height: 144, borderRadius: RAD.md, overflow: "hidden", borderWidth: 1, borderColor: C.border, backgroundColor: C.surface2 },
  body: { paddingHorizontal: SP.lg, paddingTop: SP.lg },
  title: { fontFamily: F.display, fontSize: 28, color: C.onSurface, marginLeft: 110, minHeight: 40 },
  original: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, marginLeft: 110 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: SP.md, marginTop: SP.lg },
  meta: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, textTransform: "capitalize" },
  genreRow: { flexDirection: "row", flexWrap: "wrap", gap: SP.sm, marginTop: SP.md },
  genrePill: { backgroundColor: C.surface2, borderRadius: RAD.pill, paddingHorizontal: SP.md, paddingVertical: SP.xs, borderWidth: 1, borderColor: C.border },
  genrePillText: { fontFamily: F.body, fontSize: 12, color: C.onSurface3 },
  reasonBox: { backgroundColor: C.brandTint, borderRadius: RAD.md, padding: SP.lg, marginTop: SP.lg },
  reasonHead: { fontFamily: F.medium, fontSize: 14, color: C.onBrandTint, marginBottom: SP.sm },
  reasonText: { fontFamily: F.body, fontSize: 13, color: "#FECDD3", marginTop: 2 },
  overview: { fontFamily: F.body, fontSize: 15, color: C.onSurface3, lineHeight: 22, marginTop: SP.lg },
  trailer: { flexDirection: "row", alignItems: "center", gap: SP.sm, alignSelf: "flex-start", marginTop: SP.lg, paddingHorizontal: SP.lg, paddingVertical: SP.md, borderRadius: RAD.md, borderWidth: 1, borderColor: C.borderStrong },
  trailerText: { fontFamily: F.medium, fontSize: 14, color: C.onSurface },
  detailRow: { marginTop: SP.lg },
  detailLabel: { fontFamily: F.medium, fontSize: 12, color: C.zinc, textTransform: "uppercase", letterSpacing: 0.5 },
  detailValue: { fontFamily: F.body, fontSize: 15, color: C.onSurface, marginTop: SP.xs },
  sectionHead: { fontFamily: F.display, fontSize: 20, color: C.onSurface, marginTop: SP.xxl, marginBottom: SP.md },
  stateGrid: { flexDirection: "row", flexWrap: "wrap", gap: SP.sm },
  stateBtn: { flexDirection: "row", alignItems: "center", gap: SP.sm, backgroundColor: C.surface2, borderRadius: RAD.md, borderWidth: 1, borderColor: C.border, paddingHorizontal: SP.md, paddingVertical: SP.md },
  stateBtnActive: { borderColor: C.brand, backgroundColor: C.brandTint },
  stateLabel: { fontFamily: F.medium, fontSize: 13, color: C.onSurface2 },
  review: { backgroundColor: C.surface2, borderRadius: RAD.md, padding: SP.lg, marginBottom: SP.md, borderWidth: 1, borderColor: C.border },
  reviewHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  reviewAuthor: { fontFamily: F.medium, fontSize: 14, color: C.onSurface },
  reviewReaction: { fontFamily: F.body, fontSize: 12, color: C.brand, marginTop: SP.xs, textTransform: "capitalize" },
  reviewBody: { fontFamily: F.body, fontSize: 14, color: C.onSurface3, marginTop: SP.sm, lineHeight: 20 },
  noReviews: { fontFamily: F.body, fontSize: 14, color: C.onSurface2 },
  actionBar: { position: "absolute", bottom: 0, left: 0, right: 0, flexDirection: "row", gap: SP.md, paddingHorizontal: SP.lg, paddingTop: SP.md, borderTopWidth: 1, borderTopColor: C.border },
  fabSecondary: { alignItems: "center", justifyContent: "center", paddingHorizontal: SP.lg },
  fabSecText: { fontFamily: F.body, fontSize: 11, color: C.onSurface2, marginTop: 2 },
  fabPrimary: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: SP.sm, backgroundColor: C.brand, borderRadius: RAD.md, height: 52 },
  fabPrimText: { fontFamily: F.medium, fontSize: 16, color: C.onBrand },
  sheetTitle: { fontFamily: F.display, fontSize: 22, color: C.onSurface, marginBottom: SP.lg },
  sheetLabel: { fontFamily: F.medium, fontSize: 14, color: C.onSurface2, marginTop: SP.lg, marginBottom: SP.sm },
  starRow: { flexDirection: "row", gap: SP.sm },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: SP.sm },
  reviewInput: { minHeight: 90, backgroundColor: C.surface3, borderRadius: RAD.md, padding: SP.md, color: C.onSurface, fontFamily: F.body, fontSize: 15, textAlignVertical: "top" },
  toggleRow: { marginTop: SP.lg },
  toggle: { flexDirection: "row", alignItems: "center", gap: SP.sm },
  toggleText: { fontFamily: F.body, fontSize: 14, color: C.onSurface },
  submit: { backgroundColor: C.brand, borderRadius: RAD.md, height: 52, alignItems: "center", justifyContent: "center", marginTop: SP.xxl },
  submitText: { fontFamily: F.medium, fontSize: 16, color: C.onBrand },
});
