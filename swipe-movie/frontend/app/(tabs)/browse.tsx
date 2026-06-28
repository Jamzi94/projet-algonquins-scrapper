import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import {
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { Chip, EmptyState, Loader } from "@/src/components";
import { C, F, GENRES, RAD, SP } from "@/src/theme";

const SORTS = [
  { k: "recommended", l: "For you" },
  { k: "popular", l: "Popular" },
  { k: "recent", l: "Recent" },
  { k: "rating", l: "Top rated" },
];

export default function Browse() {
  const insets = useSafeAreaInsets();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [genre, setGenre] = useState("");
  const [sort, setSort] = useState("recommended");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      if (q.trim()) {
        const stype = ["movie", "series", "anime"].includes(type) ? type : "all";
        const params = new URLSearchParams({ q, type: stype });
        const d = await api.get(`/search?${params.toString()}`);
        let items = d.results;
        if (genre) items = items.filter((c: any) => (c.genres || []).map((g: string) => g.toLowerCase()).includes(genre.toLowerCase()));
        setResults(items);
      } else {
        const params = new URLSearchParams({ q, type, genre, sort });
        const d = await api.get(`/contents?${params.toString()}`);
        setResults(d.results);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, type, genre, sort]);

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + SP.sm }]}>
        <Text style={styles.title}>Browse</Text>
        <View style={styles.search}>
          <Ionicons name="search" size={18} color={C.zinc} />
          <TextInput
            testID="browse-search-input"
            style={styles.searchInput}
            placeholder="Search titles…"
            placeholderTextColor={C.zinc}
            value={q}
            onChangeText={setQ}
            returnKeyType="search"
          />
          {q ? (
            <Pressable testID="clear-search" onPress={() => setQ("")}>
              <Ionicons name="close-circle" size={18} color={C.zinc} />
            </Pressable>
          ) : null}
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
          {["", "movie", "series", "anime"].map((t) => (
            <Chip key={t || "all"} label={t || "All"} active={type === t} onPress={() => setType(t)} testID={`type-${t || "all"}`} />
          ))}
          <View style={styles.sep} />
          {SORTS.map((s) => (
            <Chip key={s.k} label={s.l} active={sort === s.k} onPress={() => setSort(s.k)} testID={`sort-${s.k}`} />
          ))}
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
          <Chip label="All genres" active={genre === ""} onPress={() => setGenre("")} testID="genre-all" />
          {GENRES.map((g) => (
            <Chip key={g} label={g} active={genre === g} onPress={() => setGenre(g)} testID={`browse-genre-${g}`} />
          ))}
        </ScrollView>
      </View>

      {loading ? (
        <Loader />
      ) : results.length === 0 ? (
        <EmptyState icon="search-outline" title="No results" subtitle="Try clearing your filters." action="Clear filters" onAction={() => { setQ(""); setType(""); setGenre(""); }} testID="browse-empty" />
      ) : (
        <FlatList
          data={results}
          keyExtractor={(it) => it.id}
          numColumns={2}
          columnWrapperStyle={{ paddingHorizontal: SP.lg, gap: SP.md }}
          contentContainerStyle={{ paddingTop: SP.md, paddingBottom: 110, gap: SP.lg }}
          showsVerticalScrollIndicator={false}
          renderItem={({ item }) => (
            <Pressable testID={`browse-card-${item.id}`} style={styles.gridItem} onPress={() => router.push(`/content/${item.id}` as any)}>
              <View style={styles.gridPoster}>
                <Image source={{ uri: item.poster_url }} style={StyleSheet.absoluteFill} contentFit="cover" transition={200} />
              </View>
              <Text style={styles.gridTitle} numberOfLines={1}>{item.title}</Text>
              <View style={styles.badgeRow}>
                <Text style={styles.gridMeta} numberOfLines={1}>{item.year} · {item.type}</Text>
                {item.external_rating ? (
                  <View style={styles.ratePill}>
                    <Ionicons name="star" size={10} color={C.warning} />
                    <Text style={styles.ratePillText}>{Number(item.external_rating).toFixed(1)}</Text>
                  </View>
                ) : null}
              </View>
              {item.providers?.[0] ? (
                <View style={styles.provPill}>
                  <Text style={styles.provText} numberOfLines={1}>{item.providers[0]}</Text>
                </View>
              ) : null}
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { paddingHorizontal: SP.lg, borderBottomWidth: 1, borderBottomColor: C.border, paddingBottom: SP.sm },
  title: { fontFamily: F.display, fontSize: 26, color: C.onSurface, marginBottom: SP.md },
  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: SP.sm,
    backgroundColor: C.surface2,
    borderRadius: RAD.md,
    borderWidth: 1,
    borderColor: C.border,
    paddingHorizontal: SP.md,
    height: 46,
  },
  searchInput: { flex: 1, color: C.onSurface, fontFamily: F.body, fontSize: 15 },
  chipRow: { gap: SP.sm, paddingVertical: SP.sm, alignItems: "center", paddingRight: SP.lg },
  sep: { width: 1, height: 24, backgroundColor: C.border, marginHorizontal: SP.xs },
  gridItem: { flex: 1 },
  gridPoster: { width: "100%", aspectRatio: 2 / 3, borderRadius: RAD.md, overflow: "hidden", backgroundColor: C.surface2 },
  gridTitle: { fontFamily: F.medium, fontSize: 13, color: C.onSurface, marginTop: SP.sm },
  gridMeta: { fontFamily: F.body, fontSize: 11, color: C.onSurface2, marginTop: 2, textTransform: "capitalize" },
  badgeRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 2 },
  ratePill: { flexDirection: "row", alignItems: "center", gap: 2 },
  ratePillText: { fontFamily: F.medium, fontSize: 11, color: C.warning },
  provPill: { alignSelf: "flex-start", backgroundColor: C.surface3, borderRadius: RAD.sm, paddingHorizontal: SP.sm, paddingVertical: 1, marginTop: SP.xs },
  provText: { fontFamily: F.body, fontSize: 10, color: C.onSurface3 },
});
