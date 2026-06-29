import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
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

export default function Register() {
  const insets = useSafeAreaInsets();
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError("");
    setLoading(true);
    try {
      await register(email.trim(), password, username.trim());
      router.replace("/" as any);
    } catch (e: any) {
      setError(e.message || "Could not create account");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.root}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={[styles.container, { paddingTop: insets.top + SP.lg }]} keyboardShouldPersistTaps="handled">
          <Pressable testID="back-to-login" onPress={() => router.back()} style={{ marginBottom: SP.lg }}>
            <Ionicons name="chevron-back" size={26} color={C.onSurface} />
          </Pressable>
          <Text style={styles.title}>Create account</Text>
          <Text style={[T.body, { marginBottom: SP.xl }]}>Pick a pseudonymous username — stay private.</Text>

          <Text style={styles.label}>Username</Text>
          <TextInput
            testID="register-username-input"
            style={styles.input}
            placeholder="night_owl"
            placeholderTextColor={C.zinc}
            autoCapitalize="none"
            value={username}
            onChangeText={setUsername}
          />
          <Text style={styles.label}>Email</Text>
          <TextInput
            testID="register-email-input"
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
            testID="register-password-input"
            style={styles.input}
            placeholder="At least 6 characters"
            placeholderTextColor={C.zinc}
            secureTextEntry
            value={password}
            onChangeText={setPassword}
          />

          {error ? (
            <Text style={styles.error} testID="register-error">
              {error}
            </Text>
          ) : null}

          <PrimaryButton
            title={loading ? "Creating…" : "Create account"}
            onPress={submit}
            disabled={loading || !email || !password || !username}
            testID="register-submit-button"
            style={{ marginTop: SP.lg }}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  container: { paddingHorizontal: SP.xl, paddingBottom: SP.xxl },
  title: { fontFamily: F.display, fontSize: 28, color: C.onSurface, marginBottom: SP.xs },
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
});
