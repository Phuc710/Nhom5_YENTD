# Mobile App (Android)

## 📱 Screens

### 1. Login/Lookup

```
┌─────────────────┐
│  🚦 TRAFFIC     │
│    LOOKUP       │
│                 │
│ ┏━━━━━━━━━━━┓  │
│ ┃51F-12345  ┃  │
│ ┗━━━━━━━━━━━┛  │
│                 │
│ [CHECK]         │
└─────────────────┘
```

**API**: `GET /api/violations/by-plate/51F12345`

### 2. Violation List

```
┌─────────────────┐
│ 51F-12345       │
│ Total: 5        │
├─────────────────┤
│ 📷 Gò Vấp      │
│    2026-02-02   │
│    [View →]     │
├─────────────────┤
│ 📷 Củ Chi      │
│    2026-02-01   │
│    [View →]     │
└─────────────────┘
```

### 3. Violation Detail

```
┌─────────────────┐
│ [Full Image]    │
│ [Plate Crop]    │
├─────────────────┤
│ Plate: 51F12345│
│ Conf:  92.5%    │
│ Location: ...   │
│ Time: ...       │
│ [Map 📍]       │
└─────────────────┘
```

---

## 🔧 Tech Stack

- **Language**: Kotlin
- **UI**: Jetpack Compose
- **Network**: Retrofit
- **Images**: Coil

---

## 📋 Sample Code

```kotlin
@Composable
fun LoginScreen() {
    var plate by remember { mutableStateOf("") }
    
    TextField(
        value = plate,
        onValueChange = { plate = it.uppercase() },
        label = { Text("License Plate") }
    )
    
    Button(onClick = { searchViolations(plate) }) {
        Text("CHECK")
    }
}

// API call
interface ApiService {
    @GET("/api/violations/by-plate/{plate}")
    suspend fun getByPlate(@Path("plate") plate: String): List<Violation>
}
```

---

**Future**: Push notifications (FCM), Payment integration
