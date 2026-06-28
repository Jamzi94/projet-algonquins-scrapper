import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Loader, SwipeDeck, T } from "@/src/components";
import { C, F, SP } from "@/src/theme";

const DIR_TO_EVENT: any = { right: "like", left: "dislike", up: "superlike", down: "veto", tap: "neutral" };

export default function Calibration() {
  const insets = useSafeAreaInsets();
  const { refresh } = useAuth();
  const [cards, setCards] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(0);

  useEffect(() => {
    (async () => {
      const d = await api.get("/contents/calibration");
      setCards(d.results);
      setLoading(false);
    })();
  }, []);

  const finish = async () => {
    await api.put("/users/preferences", { onboarded: true });
    await refresh();
    router.replace("/" as any);
  };

  const onSwipe = (card: any, dir: string) => {
    const ev = DIR_TO_EVENT[dir];
    if (ev && ev !== "neutral") {
      api.post("/events", { content_id: card.id, event_type: ev }).catch(() => {});
    }
    setDone((d) => {
      const nd = d + 1;
      if (nd >= cards.length) setTimeout(finish, 400);
      return nd;
    });
  };

  if (loading) return <Loader label="Loading titles…" />;

  return (
    <View style={[styles.root, { paddingTop: insets.top + SP.md }]}>
      <View style={styles.header}>
        <Text style={styles.h1}>Quick calibration</Text>
        <Pressable testID="skip-calibration" onPress={finish}>
          <Text style={styles.skip}>Skip</Text>
        </Pressable>
      </View>
      <Text style={styles.sub}>
        Swipe right to like, left to skip, up to super-like. {done}/{cards.length}
      </Text>

      <View style={{ flex: 1 }}>
        <SwipeDeck
          cards={cards}
          onSwipe={onSwipe}
          emptyLabel="Calibration complete!"
          renderOverlay={(c) => (
            <View>
              <Text style={styles.cardTitle} numberOfLines={2}>
                {c.title}
              </Text>
              <Text style={[T.body, { marginTop: SP.xs }]}>
                {c.year} · {c.type} · {(c.genres || []).slice(0, 2).join(", ")}
              </Text>
            </View>
          )}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface, paddingHorizontal: SP.xl },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  h1: { fontFamily: F.display, fontSize: 24, color: C.onSurface },
  skip: { fontFamily: F.medium, fontSize: 15, color: C.brand },
  sub: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, marginTop: SP.xs, marginBottom: SP.md },
  cardTitle: { fontFamily: F.display, fontSize: 30, color: C.onSurface },
});
