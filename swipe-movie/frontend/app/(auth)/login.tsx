import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { Link, router } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAuth } from "@/src/auth";
import { PrimaryButton, T } from "@/src/components";
import { C, F, RAD, SP } from "@/src/theme";

export default function Login() {
  const insets = useSafeAreaInsets();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError("");
    setLoading(true);
    try {
      await login(email.trim(), password);
      router.replace("/" as any);
    } catch (e: any) {
      setError(e.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.root}>
      <LinearGradient colors={[C.brandTint, C.surface, C.surface]} style={StyleSheet.absoluteFill} />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={[styles.container, { paddingTop: insets.top + SP.xxxl }]} keyboardShouldPersistTaps="handled">
          <View style={styles.logoRow}>
            <Ionicons name="flame" size={34} color={C.brand} />
            <Text style={styles.logo}>SwipeNight</Text>
          </View>
          <Text style={[T.body, { marginBottom: SP.xxl }]}>
            Find what to watch — solo or with friends.
          </Text>

          <Text style={styles.label}>Email</Text>
          <TextInput
            testID="login-email-input"
            style={styles.input}
            placeholder="you@example.com"
            placeholderTextColor={C.zinc}
            autoCapitalize="none"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
          />
          <Text style={styles.label}>Password</Text>
          <TextInput
            testID="login-password-input"
            style={styles.input}
            placeholder="••••••••"
            placeholderTextColor={C.zinc}
            secureTextEntry
            value={password}
            onChangeText={setPassword}
          />

          {error ? (
            <Text style={styles.error} testID="login-error">
              {error}
            </Text>
          ) : null}

          <PrimaryButton
            title={loading ? "Signing in…" : "Sign in"}
            onPress={submit}
            disabled={loading || !email || !password}
            testID="login-submit-button"
            style={{ marginTop: SP.lg }}
          />

          <View style={styles.footer}>
            <Text style={T.body}>New here? </Text>
            <Link href={"/(auth)/register" as any} asChild>
              <Pressable testID="go-register">
                <Text style={styles.link}>Create an account</Text>
              </Pressable>
            </Link>
          </View>

          <View style={styles.demoBox}>
            <Text style={styles.demoText}>Demo account: alex_noir@swipenight.app · password123</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  container: { paddingHorizontal: SP.xl, paddingBottom: SP.xxl },
  logoRow: { flexDirection: "row", alignItems: "center", gap: SP.sm, marginBottom: SP.sm },
  logo: { fontFamily: F.display, fontSize: 32, color: C.onSurface },
  label: { fontFamily: F.medium, fontSize: 13, color: C.onSurface2, marginBottom: SP.sm, marginTop: SP.md },
  input: {
    height: 52,
    borderRadius: RAD.md,
    backgroundColor: C.surface2,
    borderWidth: 1,
    borderColor: C.border,
    paddingHorizontal: SP.lg,
    color: C.onSurface,
    fontFamily: F.body,
    fontSize: 16,
  },
  error: { color: C.error, fontFamily: F.body, marginTop: SP.md },
  footer: { flexDirection: "row", justifyContent: "center", marginTop: SP.xl },
  link: { fontFamily: F.medium, color: C.brand },
  demoBox: { marginTop: SP.xxl, padding: SP.md, borderRadius: RAD.md, backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border },
  demoText: { fontFamily: F.body, fontSize: 12, color: C.onSurface2, textAlign: "center" },
});
