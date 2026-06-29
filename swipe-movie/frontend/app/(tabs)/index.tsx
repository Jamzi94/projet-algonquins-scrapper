import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { router } from "expo-router";
import { useCallback, useState } from "react";
import { useFocusEffect } from "expo-router";
import {
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { GlassView, Loader, MatchBadge, PosterCard } from "@/src/components";
import { C, F, RAD, SP } from "@/src/theme";

export default function Home() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [feed, setFeed] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api.get("/recommendations/home");
      setFeed(d);
      // Succès : on efface tout état d'erreur précédent
      setError(false);
    } catch {
      // Échec réseau/serveur : état d'erreur distinct du « vide » légitime
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const open = (id: string) => router.push(`/content/${id}` as any);

  const retry = () => {
    setLoading(true);
    load();
  };

  if (loading) return <Loader label="Curating your night…" />;

  // État d'erreur distinct du « vide » légitime : message + possibilité de réessayer
  if (error) {
    return (
      <View style={[styles.root, styles.center, { paddingTop: insets.top }]}>
        <View style={styles.errorBox}>
          <Ionicons name="cloud-offline-outline" size={40} color={C.error} />
          <Text style={styles.errorTitle}>Impossible de charger vos recommandations</Text>
          <Text style={styles.errorMessage}>
            Vérifiez votre connexion, puis réessayez.
          </Text>
          <Pressable testID="home-retry" onPress={retry} style={styles.retryBtn}>
            <Ionicons name="refresh" size={16} color={C.onBrand} />
            <Text style={styles.retryText}>Réessayer</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const hero = feed?.hero;

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 110 }}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={C.brand} />
        }
      >
        {/* Hero */}
        {hero ? (
          <Pressable testID="home-hero" onPress={() => open(hero.content.id)} style={styles.hero}>
            <Image source={{ uri: hero.content.backdrop_url }} style={StyleSheet.absoluteFill} contentFit="cover" transition={250} />
            <LinearGradient colors={["transparent", "rgba(5,5,7,0.5)", C.surface]} style={StyleSheet.absoluteFill} />
            <View style={[styles.heroTop, { paddingTop: insets.top + SP.sm }]}>
              <Text style={styles.brand}>CineFeel</Text>
              <MatchBadge score={hero.match_score} />
            </View>
            <View style={styles.heroInfo}>
              <Text style={styles.heroTitle} numberOfLines={2}>
                {hero.content.title}
              </Text>
              {hero.reasons?.[0] ? <Text style={styles.heroReason}>{hero.reasons[0].text}</Text> : null}
              <View style={styles.heroCta}>
                <Ionicons name="play" size={16} color={C.onBrand} />
                <Text style={styles.heroCtaText}>View details</Text>
              </View>
            </View>
          </Pressable>
        ) : null}

        {(feed?.rails || []).map((rail: any) => (
          <View key={rail.context} style={{ marginTop: SP.xl }}>
            <Text style={styles.railTitle}>{rail.title}</Text>
            <FlatList
              horizontal
              data={rail.items}
              keyExtractor={(it) => rail.context + it.content.id}
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: SP.xl }}
              renderItem={({ item }) => (
                <View>
                  <PosterCard item={item.content} onPress={() => open(item.content.id)} testID={`poster-${item.content.id}`} />
                  <View style={styles.posterBadge}>
                    <GlassView style={styles.miniBadge} intensity={25}>
                      <Text style={styles.miniBadgeText}>{item.match_score}%</Text>
                    </GlassView>
                  </View>
                </View>
              )}
            />
          </View>
        ))}

        {!feed?.rails?.length ? (
          <View style={{ padding: SP.xl, alignItems: "center", marginTop: SP.xxxl }}>
            <Text style={{ fontFamily: F.body, color: C.onSurface2, textAlign: "center" }}>
              No recommendations yet. Try the calibration again from your profile.
            </Text>
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  center: { justifyContent: "center", alignItems: "center" },
  errorBox: { alignItems: "center", paddingHorizontal: SP.xl, gap: SP.md },
  errorTitle: { fontFamily: F.display, fontSize: 20, color: C.onSurface, textAlign: "center", marginTop: SP.sm },
  errorMessage: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, textAlign: "center" },
  retryBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: SP.sm,
    backgroundColor: C.brand,
    paddingHorizontal: SP.lg,
    paddingVertical: SP.md,
    borderRadius: RAD.pill,
    marginTop: SP.sm,
  },
  retryText: { fontFamily: F.medium, fontSize: 14, color: C.onBrand },
  hero: { height: 460, justifyContent: "space-between" },
  heroTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: SP.xl },
  brand: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  heroInfo: { padding: SP.xl },
  heroTitle: { fontFamily: F.display, fontSize: 34, color: C.onSurface },
  heroReason: { fontFamily: F.body, fontSize: 14, color: C.onSurface3, marginTop: SP.sm },
  heroCta: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: SP.sm,
    backgroundColor: C.brand,
    paddingHorizontal: SP.lg,
    paddingVertical: SP.md,
    borderRadius: RAD.pill,
    marginTop: SP.lg,
  },
  heroCtaText: { fontFamily: F.medium, fontSize: 14, color: C.onBrand },
  railTitle: { fontFamily: F.display, fontSize: 20, color: C.onSurface, marginBottom: SP.md, paddingHorizontal: SP.xl },
  posterBadge: { position: "absolute", top: SP.sm, left: SP.sm },
  miniBadge: { paddingHorizontal: SP.sm, paddingVertical: 2, borderRadius: RAD.sm },
  miniBadgeText: { fontFamily: F.medium, fontSize: 11, color: C.onSurface },
});
