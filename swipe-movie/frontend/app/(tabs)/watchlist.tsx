import { Image } from "expo-image";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { EmptyState, Loader } from "@/src/components";
import { C, F, RAD, SP } from "@/src/theme";

export default function Watchlist() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const d = await api.get("/watchlist");
      setItems(d.results);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + SP.sm }]}>
        <Text style={styles.title}>Watchlist</Text>
      </View>
      {loading ? (
        <Loader />
      ) : items.length === 0 ? (
        <EmptyState icon="bookmark-outline" title="Your watchlist is empty" subtitle="Tap the bookmark on any title to save it here." action="Browse titles" onAction={() => router.push("/(tabs)/browse" as any)} testID="watchlist-empty" />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(it) => it.id}
          numColumns={2}
          columnWrapperStyle={{ paddingHorizontal: SP.lg, gap: SP.md }}
          contentContainerStyle={{ paddingTop: SP.md, paddingBottom: 110, gap: SP.lg }}
          showsVerticalScrollIndicator={false}
          renderItem={({ item }) => (
            <Pressable testID={`watchlist-card-${item.id}`} style={styles.gridItem} onPress={() => router.push(`/content/${item.id}` as any)}>
              <View style={styles.gridPoster}>
                <Image source={{ uri: item.poster_url }} style={StyleSheet.absoluteFill} contentFit="cover" transition={200} />
              </View>
              <Text style={styles.gridTitle} numberOfLines={1}>{item.title}</Text>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { paddingHorizontal: SP.lg, marginBottom: SP.sm },
  title: { fontFamily: F.display, fontSize: 26, color: C.onSurface },
  gridItem: { flex: 1 },
  gridPoster: { width: "100%", aspectRatio: 2 / 3, borderRadius: RAD.md, overflow: "hidden", backgroundColor: C.surface2 },
  gridTitle: { fontFamily: F.medium, fontSize: 13, color: C.onSurface, marginTop: SP.sm },
});
