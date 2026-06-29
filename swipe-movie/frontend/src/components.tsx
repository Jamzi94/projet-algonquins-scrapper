import { Ionicons } from "@expo/vector-icons";
import { BlurView } from "expo-blur";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Dimensions,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { C, F, RAD, SP } from "@/src/theme";

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get("window");

export function GlassView({ children, style, intensity = 40 }: any) {
  return (
    <BlurView intensity={intensity} tint="dark" style={[styles.glass, style]}>
      {children}
    </BlurView>
  );
}

export function Loader({ label }: { label?: string }) {
  return (
    <View style={styles.center} testID="loader">
      <ActivityIndicator color={C.brand} size="large" />
      {label ? <Text style={styles.muted}>{label}</Text> : null}
    </View>
  );
}

export function EmptyState({ icon = "film-outline", title, subtitle, action, onAction, testID }: any) {
  return (
    <View style={styles.center} testID={testID || "empty-state"}>
      <Ionicons name={icon} size={48} color={C.zinc} />
      <Text style={[styles.h2, { marginTop: SP.md }]}>{title}</Text>
      {subtitle ? <Text style={[styles.muted, { textAlign: "center", marginTop: SP.xs }]}>{subtitle}</Text> : null}
      {action ? (
        <View style={{ marginTop: SP.lg }}>
          <PrimaryButton title={action} onPress={onAction} testID="empty-action" />
        </View>
      ) : null}
    </View>
  );
}

export function PrimaryButton({ title, onPress, style, disabled, testID, icon }: any) {
  return (
    <Pressable
      testID={testID}
      disabled={disabled}
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        onPress?.();
      }}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: disabled ? C.surface3 : C.brand, opacity: pressed ? 0.85 : 1 },
        style,
      ]}
    >
      {icon ? <Ionicons name={icon} size={18} color={C.onBrand} style={{ marginRight: SP.sm }} /> : null}
      <Text style={styles.btnText}>{title}</Text>
    </Pressable>
  );
}

export function GhostButton({ title, onPress, style, testID, icon }: any) {
  return (
    <Pressable
      testID={testID}
      onPress={() => {
        Haptics.selectionAsync().catch(() => {});
        onPress?.();
      }}
      style={({ pressed }) => [styles.ghost, { opacity: pressed ? 0.7 : 1 }, style]}
    >
      {icon ? <Ionicons name={icon} size={18} color={C.onSurface} style={{ marginRight: SP.sm }} /> : null}
      <Text style={styles.ghostText}>{title}</Text>
    </Pressable>
  );
}

export function Chip({ label, active, onPress, testID }: any) {
  return (
    <Pressable
      testID={testID}
      onPress={() => {
        Haptics.selectionAsync().catch(() => {});
        onPress?.();
      }}
      style={[styles.chip, active && styles.chipActive]}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

export function MatchBadge({ score, style }: { score: number; style?: ViewStyle }) {
  const color = score >= 75 ? C.success : score >= 50 ? C.warning : C.zinc;
  return (
    <GlassView style={[styles.matchBadge, style]} intensity={30}>
      <View style={[styles.matchDot, { backgroundColor: color }]} />
      <Text style={styles.matchText}>{score}% match</Text>
    </GlassView>
  );
}

export function Stars({ value = 0, size = 16 }: { value?: number; size?: number }) {
  return (
    <View style={{ flexDirection: "row" }}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Ionicons
          key={i}
          name={value >= i ? "star" : value >= i - 0.5 ? "star-half" : "star-outline"}
          size={size}
          color={C.warning}
        />
      ))}
    </View>
  );
}

export function PosterCard({ item, onPress, width = 132, showTitle = true, testID }: any) {
  return (
    <Pressable testID={testID} onPress={onPress} style={{ width, marginRight: SP.md }}>
      <View style={[styles.poster, { width, height: width * 1.5 }]}>
        <Image source={{ uri: item.poster_url }} style={StyleSheet.absoluteFill} contentFit="cover" transition={200} />
      </View>
      {showTitle ? (
        <Text style={styles.posterTitle} numberOfLines={1}>
          {item.title}
        </Text>
      ) : null}
      {showTitle ? (
        <Text style={styles.posterMeta} numberOfLines={1}>
          {item.year} · {item.type}
        </Text>
      ) : null}
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// SwipeDeck — Tinder-style. directions: right=like, left=dislike, up=superlike,
// down=veto, tap=neutral.
// ---------------------------------------------------------------------------
type Dir = "right" | "left" | "up" | "down" | "tap";

export function SwipeDeck({
  cards,
  onSwipe,
  renderOverlay,
  emptyLabel = "All done!",
}: {
  cards: any[];
  onSwipe: (card: any, dir: Dir) => void;
  renderOverlay?: (card: any) => React.ReactNode;
  emptyLabel?: string;
}) {
  const [index, setIndex] = useState(0);
  const x = useSharedValue(0);
  const y = useSharedValue(0);
  // Indique si le composant est toujours monté : empêche tout callback
  // d'animation (runOnJS) d'agir après le démontage.
  const mounted = useRef(true);

  // Bug #2 : réinitialise l'index et la position quand la prop `cards` change
  // d'identité, sinon un index périmé affiche les mauvaises cartes.
  useEffect(() => {
    setIndex(0);
    x.value = 0;
    y.value = 0;
  }, [cards]);

  // Nettoyage au démontage : invalide le drapeau pour que `advance` n'exécute
  // plus rien si une animation se termine après le démontage.
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const current = cards[index];
  const next = cards[index + 1];

  const advance = (dir: Dir) => {
    // Bug #1 : ne rien faire si le composant a été démonté entre-temps.
    if (!mounted.current) return;
    const card = cards[index];
    if (card) onSwipe(card, dir);
    setIndex((i) => i + 1);
    x.value = 0;
    y.value = 0;
  };

  const fling = (dir: Dir) => {
    Haptics.impactAsync(
      dir === "up" ? Haptics.ImpactFeedbackStyle.Heavy : Haptics.ImpactFeedbackStyle.Medium
    ).catch(() => {});
    // Bug #1 : on synchronise l'avancement sur la fin réelle de l'animation
    // (callback de withTiming) au lieu d'un setTimeout fixe (200ms) décorrélé
    // de la durée d'animation et non nettoyé au démontage.
    const done = (finished?: boolean) => {
      "worklet";
      if (finished) runOnJS(advance)(dir);
    };
    if (dir === "right") x.value = withTiming(SCREEN_W * 1.4, { duration: 250 }, done);
    else if (dir === "left") x.value = withTiming(-SCREEN_W * 1.4, { duration: 250 }, done);
    else if (dir === "up") y.value = withTiming(-SCREEN_H, { duration: 250 }, done);
    else if (dir === "down") y.value = withTiming(SCREEN_H, { duration: 250 }, done);
  };

  const pan = Gesture.Pan()
    .onUpdate((e) => {
      x.value = e.translationX;
      y.value = e.translationY;
    })
    .onEnd((e) => {
      const TH = 110;
      if (Math.abs(e.translationX) > Math.abs(e.translationY)) {
        if (e.translationX > TH) {
          x.value = withTiming(SCREEN_W * 1.4, { duration: 220 });
          runOnJS(advance)("right");
          return;
        }
        if (e.translationX < -TH) {
          x.value = withTiming(-SCREEN_W * 1.4, { duration: 220 });
          runOnJS(advance)("left");
          return;
        }
      } else {
        if (e.translationY < -TH) {
          y.value = withTiming(-SCREEN_H, { duration: 220 });
          runOnJS(advance)("up");
          return;
        }
        if (e.translationY > TH) {
          y.value = withTiming(SCREEN_H, { duration: 220 });
          runOnJS(advance)("down");
          return;
        }
      }
      x.value = withSpring(0);
      y.value = withSpring(0);
    });

  const cardStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: x.value },
      { translateY: y.value },
      { rotate: `${interpolate(x.value, [-SCREEN_W, SCREEN_W], [-12, 12])}deg` },
    ],
  }));

  const likeStyle = useAnimatedStyle(() => ({ opacity: interpolate(x.value, [0, 120], [0, 1]) }));
  const nopeStyle = useAnimatedStyle(() => ({ opacity: interpolate(x.value, [-120, 0], [1, 0]) }));
  const superStyle = useAnimatedStyle(() => ({ opacity: interpolate(y.value, [-120, 0], [1, 0]) }));
  const vetoStyle = useAnimatedStyle(() => ({ opacity: interpolate(y.value, [0, 120], [0, 1]) }));

  if (!current) {
    return (
      <View style={styles.deckWrap}>
        <EmptyState icon="checkmark-done-outline" title={emptyLabel} testID="deck-empty" />
      </View>
    );
  }

  return (
    <View style={styles.deckWrap}>
      {next ? (
        <View style={[styles.deckCard, { transform: [{ scale: 0.94 }, { translateY: 14 }] }]}>
          <Image source={{ uri: next.backdrop_url || next.poster_url }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["transparent", "rgba(5,5,7,0.3)", C.surface]} style={StyleSheet.absoluteFill} />
        </View>
      ) : null}
      <GestureDetector gesture={pan}>
        <Animated.View style={[styles.deckCard, cardStyle]} testID="swipe-card">
          <Image source={{ uri: current.backdrop_url || current.poster_url }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["transparent", "rgba(5,5,7,0.4)", C.surface]} style={StyleSheet.absoluteFill} />

          <Animated.View style={[styles.tag, styles.tagLike, likeStyle]}>
            <Text style={styles.tagText}>LIKE</Text>
          </Animated.View>
          <Animated.View style={[styles.tag, styles.tagNope, nopeStyle]}>
            <Text style={styles.tagText}>NOPE</Text>
          </Animated.View>
          <Animated.View style={[styles.tag, styles.tagSuper, superStyle]}>
            <Text style={styles.tagText}>SUPER</Text>
          </Animated.View>
          <Animated.View style={[styles.tag, styles.tagVeto, vetoStyle]}>
            <Text style={styles.tagText}>VETO</Text>
          </Animated.View>

          <View style={styles.deckInfo}>{renderOverlay ? renderOverlay(current) : null}</View>
        </Animated.View>
      </GestureDetector>

      <View style={styles.deckActions}>
        <ActionBtn icon="close" color={C.zinc} onPress={() => fling("left")} testID="deck-dislike" />
        <ActionBtn icon="arrow-down" color={C.error} small onPress={() => fling("down")} testID="deck-veto" />
        <ActionBtn icon="ellipse-outline" color={C.onSurface2} small onPress={() => advance("tap")} testID="deck-neutral" />
        <ActionBtn icon="arrow-up" color={C.warning} small onPress={() => fling("up")} testID="deck-superlike" />
        <ActionBtn icon="heart" color={C.success} onPress={() => fling("right")} testID="deck-like" />
      </View>
    </View>
  );
}

function ActionBtn({ icon, color, onPress, small, testID }: any) {
  const size = small ? 48 : 60;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [
        styles.actionBtn,
        { width: size, height: size, borderRadius: size / 2, borderColor: color, opacity: pressed ? 0.6 : 1 },
      ]}
    >
      <Ionicons name={icon} size={small ? 22 : 28} color={color} />
    </Pressable>
  );
}

export const T = StyleSheet.create({
  h1: { fontFamily: F.display, fontSize: 28, color: C.onSurface },
  h2: { fontFamily: F.display, fontSize: 20, color: C.onSurface },
  title: { fontFamily: F.medium, fontSize: 16, color: C.onSurface },
  body: { fontFamily: F.body, fontSize: 14, color: C.onSurface2 },
  small: { fontFamily: F.body, fontSize: 12, color: C.onSurface2 },
});

const styles = StyleSheet.create({
  glass: { backgroundColor: C.glass, overflow: "hidden" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: SP.xl },
  muted: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, marginTop: SP.sm },
  h2: { fontFamily: F.display, fontSize: 20, color: C.onSurface },
  btn: {
    height: 52,
    borderRadius: RAD.md,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    paddingHorizontal: SP.xl,
  },
  btnText: { fontFamily: F.medium, fontSize: 16, color: C.onBrand },
  ghost: {
    height: 52,
    borderRadius: RAD.md,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    borderWidth: 1,
    borderColor: C.borderStrong,
    paddingHorizontal: SP.xl,
  },
  ghostText: { fontFamily: F.medium, fontSize: 16, color: C.onSurface },
  chip: {
    height: 36,
    paddingHorizontal: SP.lg,
    borderRadius: RAD.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: C.surface2,
    borderWidth: 1,
    borderColor: C.border,
    flexShrink: 0,
  },
  chipActive: { backgroundColor: C.brandTint, borderColor: C.brand },
  chipText: { fontFamily: F.medium, fontSize: 13, color: C.onSurface2 },
  chipTextActive: { color: C.onBrandTint },
  matchBadge: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: SP.md,
    paddingVertical: SP.xs,
    borderRadius: RAD.pill,
    borderWidth: 1,
    borderColor: C.border,
  },
  matchDot: { width: 8, height: 8, borderRadius: 4, marginRight: SP.sm },
  matchText: { fontFamily: F.medium, fontSize: 12, color: C.onSurface },
  poster: { borderRadius: RAD.md, overflow: "hidden", backgroundColor: C.surface2 },
  posterTitle: { fontFamily: F.medium, fontSize: 13, color: C.onSurface, marginTop: SP.sm },
  posterMeta: { fontFamily: F.body, fontSize: 11, color: C.onSurface2, marginTop: 2, textTransform: "capitalize" },
  // deck
  deckWrap: { flex: 1, alignItems: "center", justifyContent: "center" },
  deckCard: {
    position: "absolute",
    top: 0,
    width: SCREEN_W - SP.xl * 2,
    height: SCREEN_H * 0.6,
    borderRadius: RAD.lg,
    overflow: "hidden",
    backgroundColor: C.surface2,
    borderWidth: 1,
    borderColor: C.border,
  },
  deckInfo: { position: "absolute", bottom: 0, left: 0, right: 0, padding: SP.xl },
  deckActions: {
    position: "absolute",
    bottom: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: SP.lg,
  },
  actionBtn: {
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    backgroundColor: C.glass,
  },
  tag: {
    position: "absolute",
    top: 28,
    paddingHorizontal: SP.md,
    paddingVertical: SP.sm,
    borderRadius: RAD.sm,
    borderWidth: 3,
  },
  tagText: { fontFamily: F.medium, fontSize: 22, color: C.onSurface, letterSpacing: 2 },
  tagLike: { right: 24, borderColor: C.success, transform: [{ rotate: "12deg" }] },
  tagNope: { left: 24, borderColor: C.zinc, transform: [{ rotate: "-12deg" }] },
  tagSuper: { alignSelf: "center", left: 0, right: 0, top: 60, alignItems: "center", borderColor: C.warning },
  tagVeto: { alignSelf: "center", left: 0, right: 0, bottom: 100, top: undefined, alignItems: "center", borderColor: C.error },
});
