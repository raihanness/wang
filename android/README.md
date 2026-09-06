# Wang — Native Android WebView App (Option 3)

This is a complete, standalone native Android Studio project that wraps your hosted **Wang** money tracker web application inside an optimized native Android `WebView`.

---

## Key Features

- **Standalone Native App**: Appears with its own launcher icon, splash background, and full-screen layout without any browser address bars or navigation chrome.
- **Camera & Gallery Photo Attachments**: Complete `WebChromeClient.onShowFileChooser()` implementation with `FileProvider` so tapping the camera icon in Wang opens the Android camera or photo gallery seamlessly for receipt uploads.
- **Session & Cookie Persistence**: Fully integrates Android `CookieManager` with automatic flushing on pause/resume so your login session stays alive across app launches.
- **Hardware Acceleration & Sound**: Hardware accelerated rendering for 60fps Chart.js charts and pastel bottom sheet animations, plus gesture-free Web Audio synthesizer support for tactile feedback.
- **Pull-to-Refresh**: Native `SwipeRefreshLayout` with Wang primary peach/mint color scheme.
- **Smart Back Navigation**: Back gestures and physical back buttons navigate WebView page history (`webView.goBack()`) before exiting the application.
- **Live Automatic Updates**: Because the WebView loads your live DOM Cloud URL, any changes you deploy to DOM Cloud are immediately reflected in the app without reinstalling the APK.

---

## How to Build the APK in Android Studio

### 1. Configure Your Hosted Domain URL
Open [`app/src/main/res/values/strings.xml`](file:///x:/!%20projects/wang/android/app/src/main/res/values/strings.xml) and update `app_web_url` to your live hosted DOM Cloud instance:
```xml
<string name="app_web_url">https://your-app.domcloud.dev</string>
```

### 2. Open Project in Android Studio
1. Open **Android Studio**.
2. Click **File > Open...** (or **Open an Existing Project** on the welcome screen).
3. Navigate to and select the `android/` folder inside this repository.
4. Android Studio will automatically sync Gradle and download required Android SDK dependencies.

### 3. Build & Install the APK
- **Directly to your phone via USB**:
  1. Enable **Developer Options** and **USB Debugging** on your Android phone.
  2. Connect your phone to your computer via USB cable.
  3. Select your phone from the device dropdown at the top of Android Studio.
  4. Click the green **Run (▶)** button.
- **Export standalone APK file**:
  1. Click **Build > Build Bundle(s) / APK(s) > Build APK(s)** in the top menu.
  2. Once built, click **locate** in the popup notification to find `app-debug.apk` (usually in `app/build/outputs/apk/debug/`).
  3. Send or copy `app-debug.apk` to your phone and tap to install!
