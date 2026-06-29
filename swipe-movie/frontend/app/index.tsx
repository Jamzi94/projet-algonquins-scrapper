import { Redirect } from "expo-router";
import { View } from "react-native";

import { useAuth } from "@/src/auth";
import { Loader } from "@/src/components";
import { C } from "@/src/theme";

export default function Index() {
  const { ready, user } = useAuth();

  if (!ready) {
    return (
      <View style={{ flex: 1, backgroundColor: C.surface }}>
        <Loader label="CineFeel" />
      </View>
    );
  }
  if (!user) return <Redirect href={"/(auth)/login" as any} />;
  if (!user.preferences?.onboarded) return <Redirect href={"/onboarding/preferences" as any} />;
  return <Redirect href={"/(tabs)" as any} />;
}
