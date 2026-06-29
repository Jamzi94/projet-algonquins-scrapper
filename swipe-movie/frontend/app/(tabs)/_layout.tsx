import { Ionicons } from "@expo/vector-icons";
import { BlurView } from "expo-blur";
import { Tabs } from "expo-router";
import { StyleSheet } from "react-native";

import { C, F } from "@/src/theme";

const ICONS: any = {
  index: "home",
  browse: "search",
  rooms: "people",
  watchlist: "bookmark",
  profile: "person",
};

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: C.brand,
        tabBarInactiveTintColor: C.zinc,
        tabBarStyle: styles.bar,
        tabBarLabelStyle: { fontFamily: F.medium, fontSize: 11 },
        tabBarBackground: () => <BlurView intensity={50} tint="dark" style={StyleSheet.absoluteFill} />,
        tabBarIcon: ({ color, size, focused }) => (
          <Ionicons name={focused ? ICONS[route.name] : `${ICONS[route.name]}-outline`} size={size} color={color} />
        ),
      })}
    >
      <Tabs.Screen name="index" options={{ title: "Home" }} />
      <Tabs.Screen name="browse" options={{ title: "Browse" }} />
      <Tabs.Screen name="rooms" options={{ title: "Rooms" }} />
      <Tabs.Screen name="watchlist" options={{ title: "Watchlist" }} />
      <Tabs.Screen name="profile" options={{ title: "Profile" }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  bar: {
    position: "absolute",
    backgroundColor: "rgba(5,5,7,0.7)",
    borderTopColor: C.border,
    borderTopWidth: 1,
    elevation: 0,
  },
});
