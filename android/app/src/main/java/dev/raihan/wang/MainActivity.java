package dev.raihan.wang;

import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResult;
import androidx.activity.result.ActivityResultCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.biometric.BiometricManager;
import androidx.biometric.BiometricPrompt;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class MainActivity extends AppCompatActivity {

    public static final String PREFS_NAME = "wang_prefs";
    public static final String KEY_BIOMETRIC_ENABLED = "biometric_enabled";
    public static final String KEY_HAPTICS_ENABLED = "haptics_enabled";

    private WebView mWebView;
    private SwipeRefreshLayout mSwipeRefresh;
    private View mBiometricLockOverlay;
    private ValueCallback<Uri[]> mFilePathCallback;
    private String mCameraPhotoPath;
    private Uri mCameraPhotoUri;
    private String mPendingCapturedPhotoBase64;
    private ActivityResultLauncher<Intent> mFileChooserLauncher;
    private ActivityResultLauncher<String> mNotificationPermissionLauncher;
    private int mPendingReminderHour = 20;
    private int mPendingReminderMinute = 0;

    // Vibrator engine
    private Vibrator mVibrator;
    private boolean mHapticsEnabled = true;

    // Biometric security
    private boolean mIsAppLocked = false;
    private long mLastPausedTimestamp = 0;
    private static final long LOCK_GRACE_PERIOD_MS = 60000; // 1 minute grace period before locking on resume

    // Pull-to-refresh & scroll states
    private volatile boolean mPageAllowsRefresh = true;
    private volatile boolean mIsScrollableActive = false;

    // System bar insets in dp
    private int mLastTopInsetsDp = 0;
    private int mLastBottomInsetsDp = 0;

    public class WebAppInterface {
        @JavascriptInterface
        public void setPullToRefreshEnabled(boolean enabled) {
            mPageAllowsRefresh = enabled;
            runOnUiThread(() -> syncSwipeRefreshState());
        }

        @JavascriptInterface
        public void setScrollableActive(boolean active) {
            mIsScrollableActive = active;
            runOnUiThread(() -> syncSwipeRefreshState());
        }

        @JavascriptInterface
        public void setSystemTheme(boolean isDark) {
            runOnUiThread(() -> updateSystemBarIcons(isDark));
        }

        @JavascriptInterface
        public String getPendingCapturedPhoto() {
            String photo = mPendingCapturedPhotoBase64;
            mPendingCapturedPhotoBase64 = null;
            return photo != null ? photo : "";
        }

        @JavascriptInterface
        public void downloadUrl(String url) {
            runOnUiThread(() -> {
                if (mWebView != null) {
                    handleDownload(url, mWebView.getSettings().getUserAgentString(), null, "text/csv");
                }
            });
        }

        // ── Native Haptics Bridge ──
        @JavascriptInterface
        public void vibrateEffect(String effect) {
            performHaptic(effect);
        }

        @JavascriptInterface
        public boolean isHapticsEnabled() {
            return mHapticsEnabled;
        }

        @JavascriptInterface
        public void setHapticsEnabled(boolean enabled) {
            mHapticsEnabled = enabled;
            getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .putBoolean(KEY_HAPTICS_ENABLED, enabled)
                    .apply();
        }

        // ── Native Biometrics Bridge ──
        @JavascriptInterface
        public boolean isBiometricAvailable() {
            BiometricManager bm = BiometricManager.from(MainActivity.this);
            int canAuth = bm.canAuthenticate(
                    BiometricManager.Authenticators.BIOMETRIC_STRONG |
                    BiometricManager.Authenticators.DEVICE_CREDENTIAL
            );
            return canAuth == BiometricManager.BIOMETRIC_SUCCESS;
        }

        @JavascriptInterface
        public boolean isBiometricEnabled() {
            return getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getBoolean(KEY_BIOMETRIC_ENABLED, false);
        }

        @JavascriptInterface
        public void setBiometricEnabled(boolean enabled) {
            runOnUiThread(() -> {
                if (enabled) {
                    promptBiometricToEnable();
                } else {
                    getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                            .edit()
                            .putBoolean(KEY_BIOMETRIC_ENABLED, false)
                            .apply();
                    notifyWebBiometricState(false);
                    Toast.makeText(MainActivity.this, "Biometric app lock disabled", Toast.LENGTH_SHORT).show();
                }
            });
        }

        // ── Native Daily Reminder Bridge ──
        @JavascriptInterface
        public boolean isReminderEnabled() {
            return getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                    .getBoolean(DailyReminderReceiver.KEY_REMINDER_ENABLED, false);
        }

        @JavascriptInterface
        public int getReminderHour() {
            return getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                    .getInt(DailyReminderReceiver.KEY_REMINDER_HOUR, 20);
        }

        @JavascriptInterface
        public int getReminderMinute() {
            return getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                    .getInt(DailyReminderReceiver.KEY_REMINDER_MINUTE, 0);
        }

        @JavascriptInterface
        public void setDailyReminder(boolean enabled, int hour, int minute) {
            runOnUiThread(() -> {
                if (enabled) {
                    mPendingReminderHour = hour;
                    mPendingReminderMinute = minute;

                    // On Android 13+ (API 33+), check if notification permission needs to be requested
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                            ContextCompat.checkSelfPermission(MainActivity.this, android.Manifest.permission.POST_NOTIFICATIONS)
                                    != PackageManager.PERMISSION_GRANTED) {
                        try {
                            mNotificationPermissionLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS);
                        } catch (Exception e) {
                            Toast.makeText(MainActivity.this, "Cannot request notification permission", Toast.LENGTH_SHORT).show();
                        }
                        return;
                    }

                    // Permission is already granted or not needed on pre-Android 13
                    applyAndScheduleReminder(hour, minute);
                } else {
                    getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit()
                            .putBoolean(DailyReminderReceiver.KEY_REMINDER_ENABLED, false)
                            .apply();
                    DailyReminderReceiver.cancelReminder(MainActivity.this);
                    notifyWebReminderState(false);
                    Toast.makeText(MainActivity.this, "Daily reminder turned off", Toast.LENGTH_SHORT).show();
                }
            });
        }
    }

    private void updateSystemBarIcons(boolean isDark) {
        Window window = getWindow();
        WindowInsetsControllerCompat insetsController = WindowCompat.getInsetsController(window, window.getDecorView());
        if (insetsController != null) {
            insetsController.setAppearanceLightStatusBars(!isDark);
            insetsController.setAppearanceLightNavigationBars(!isDark);
        }
        if (mBiometricLockOverlay != null) {
            mBiometricLockOverlay.setBackgroundColor(isDark ? getColor(R.color.bg_dark) : getColor(R.color.bg_light));
        }
    }

    private void setupEdgeToEdgeInsets() {
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.root_container), (v, windowInsets) -> {
            Insets insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars());
            float density = getResources().getDisplayMetrics().density;
            int topDp = Math.round(insets.top / density);
            int bottomDp = Math.round(insets.bottom / density);

            mLastTopInsetsDp = topDp;
            mLastBottomInsetsDp = bottomDp;

            injectSafeAreaInsets(topDp, bottomDp);
            return windowInsets;
        });
    }

    private void injectSafeAreaInsets(int topDp, int bottomDp) {
        if (mWebView != null && (topDp > 0 || bottomDp > 0)) {
            String js = "document.documentElement.style.setProperty('--safe-area-top', '" + topDp + "px');" +
                        "document.documentElement.style.setProperty('--safe-area-bottom', '" + bottomDp + "px');";
            mWebView.evaluateJavascript(js, null);
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Edge-to-Edge display with transparent system bars
        Window window = getWindow();
        WindowCompat.setDecorFitsSystemWindows(window, false);
        window.setStatusBarColor(Color.TRANSPARENT);
        window.setNavigationBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            window.setStatusBarContrastEnforced(false);
            window.setNavigationBarContrastEnforced(false);
        }

        setContentView(R.layout.activity_main);

        // Initialize system bar icons based on system night mode
        int nightMode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        updateSystemBarIcons(nightMode == Configuration.UI_MODE_NIGHT_YES);

        // Setup Edge-to-Edge window insets
        setupEdgeToEdgeInsets();

        // Initialize hardware vibrator service
        setupVibrator();

        // SharedPreferences
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        mHapticsEnabled = prefs.getBoolean(KEY_HAPTICS_ENABLED, true);

        // Views
        mWebView = findViewById(R.id.web_view);
        mSwipeRefresh = findViewById(R.id.swipe_refresh);
        mBiometricLockOverlay = findViewById(R.id.biometric_lock_overlay);

        findViewById(R.id.btn_unlock_biometric).setOnClickListener(v -> {
            performHaptic("click");
            showBiometricPromptForUnlock();
        });

        // Setup Notification Permission Launcher
        mNotificationPermissionLauncher = registerForActivityResult(
                new ActivityResultContracts.RequestPermission(),
                isGranted -> {
                    if (isGranted) {
                        applyAndScheduleReminder(mPendingReminderHour, mPendingReminderMinute);
                    } else {
                        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit()
                                .putBoolean(DailyReminderReceiver.KEY_REMINDER_ENABLED, false)
                                .apply();
                        notifyWebReminderState(false);
                        Toast.makeText(this, "Notification permission is required for daily reminders", Toast.LENGTH_LONG).show();
                    }
                }
        );

        // Configure SwipeRefreshLayout with Wang pastel primary & accent colors
        mSwipeRefresh.setColorSchemeColors(
                getColor(R.color.primary),
                getColor(R.color.accent)
        );
        mSwipeRefresh.setOnRefreshListener(() -> mWebView.reload());

        // Fix scroll-to-refresh conflict
        mSwipeRefresh.setOnChildScrollUpCallback((parent, child) -> {
            if (!mPageAllowsRefresh || mIsScrollableActive) {
                return true;
            }
            return mWebView.canScrollVertically(-1) || mWebView.getScrollY() > 0;
        });

        mWebView.setOnScrollChangeListener((v, scrollX, scrollY, oldScrollX, oldScrollY) -> {
            syncSwipeRefreshState();
        });

        // File chooser for receipts
        setupFileChooserLauncher();

        // Setup WebView
        setupWebView();

        // Setup smart back navigation (handles sheets before history/exit)
        setupBackNavigation();

        // Check Biometric lock on startup
        if (prefs.getBoolean(KEY_BIOMETRIC_ENABLED, false)) {
            lockAppWithBiometrics();
        }

        // Determine initial URL (handles shortcuts and deep links)
        String initialUrl = getUrlFromIntent(getIntent());
        if (savedInstanceState != null) {
            mWebView.restoreState(savedInstanceState);
            mCameraPhotoPath = savedInstanceState.getString("camera_photo_path");
            mPendingCapturedPhotoBase64 = savedInstanceState.getString("pending_photo_base64");
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                mCameraPhotoUri = savedInstanceState.getParcelable("camera_photo_uri", Uri.class);
            } else {
                mCameraPhotoUri = savedInstanceState.getParcelable("camera_photo_uri");
            }
        }
        if (mWebView.getUrl() == null) {
            mWebView.loadUrl(initialUrl);
        }
    }

    private void setupVibrator() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            VibratorManager vm = (VibratorManager) getSystemService(Context.VIBRATOR_MANAGER_SERVICE);
            if (vm != null) {
                mVibrator = vm.getDefaultVibrator();
            }
        } else {
            mVibrator = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
        }
    }

    public void performHaptic(String effect) {
        if (!mHapticsEnabled || mVibrator == null || !mVibrator.hasVibrator()) {
            return;
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                switch (effect) {
                    case "tap":
                        mVibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK));
                        break;
                    case "click":
                        mVibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_CLICK));
                        break;
                    case "heavy":
                        mVibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_HEAVY_CLICK));
                        break;
                    case "success":
                        mVibrator.vibrate(VibrationEffect.createWaveform(
                                new long[]{0, 12, 35, 18},
                                new int[]{0, 110, 0, 190},
                                -1
                        ));
                        break;
                    case "delete":
                    case "error":
                        mVibrator.vibrate(VibrationEffect.createWaveform(
                                new long[]{0, 20, 40, 25},
                                new int[]{0, 160, 0, 190},
                                -1
                        ));
                        break;
                    default:
                        mVibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK));
                        break;
                }
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                mVibrator.vibrate(VibrationEffect.createOneShot(12, VibrationEffect.DEFAULT_AMPLITUDE));
            } else {
                mVibrator.vibrate(12);
            }
        } catch (Exception ignored) {}
    }

    // ── Biometric Authentication ──

    private void lockAppWithBiometrics() {
        mIsAppLocked = true;
        if (mBiometricLockOverlay != null) {
            mBiometricLockOverlay.setVisibility(View.VISIBLE);
            mBiometricLockOverlay.setAlpha(1f);
        }
        showBiometricPromptForUnlock();
    }

    private void unlockAppWithBiometrics() {
        mIsAppLocked = false;
        performHaptic("success");
        if (mBiometricLockOverlay != null) {
            mBiometricLockOverlay.animate()
                    .alpha(0f)
                    .setDuration(220)
                    .withEndAction(() -> mBiometricLockOverlay.setVisibility(View.GONE))
                    .start();
        }
    }

    private void showBiometricPromptForUnlock() {
        BiometricPrompt.PromptInfo promptInfo;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            promptInfo = new BiometricPrompt.PromptInfo.Builder()
                    .setTitle(getString(R.string.biometric_title))
                    .setSubtitle(getString(R.string.biometric_subtitle))
                    .setAllowedAuthenticators(
                            BiometricManager.Authenticators.BIOMETRIC_STRONG |
                            BiometricManager.Authenticators.DEVICE_CREDENTIAL
                    )
                    .build();
        } else {
            promptInfo = new BiometricPrompt.PromptInfo.Builder()
                    .setTitle(getString(R.string.biometric_title))
                    .setSubtitle(getString(R.string.biometric_subtitle))
                    .setDeviceCredentialAllowed(true)
                    .build();
        }

        BiometricPrompt biometricPrompt = new BiometricPrompt(
                this,
                ContextCompat.getMainExecutor(this),
                new BiometricPrompt.AuthenticationCallback() {
                    @Override
                    public void onAuthenticationSucceeded(@NonNull BiometricPrompt.AuthenticationResult result) {
                        super.onAuthenticationSucceeded(result);
                        unlockAppWithBiometrics();
                    }

                    @Override
                    public void onAuthenticationError(int errorCode, @NonNull CharSequence errString) {
                        super.onAuthenticationError(errorCode, errString);
                        // Remain locked; user can tap unlock button
                    }

                    @Override
                    public void onAuthenticationFailed() {
                        super.onAuthenticationFailed();
                        performHaptic("error");
                    }
                }
        );

        try {
            biometricPrompt.authenticate(promptInfo);
        } catch (Exception e) {
            // Fallback unlock if device lacks lock mechanism
            unlockAppWithBiometrics();
        }
    }

    private void promptBiometricToEnable() {
        BiometricPrompt.PromptInfo promptInfo;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            promptInfo = new BiometricPrompt.PromptInfo.Builder()
                    .setTitle("Verify Identity")
                    .setSubtitle("Confirm fingerprint or lock to enable Wang App Lock")
                    .setAllowedAuthenticators(
                            BiometricManager.Authenticators.BIOMETRIC_STRONG |
                            BiometricManager.Authenticators.DEVICE_CREDENTIAL
                    )
                    .build();
        } else {
            promptInfo = new BiometricPrompt.PromptInfo.Builder()
                    .setTitle("Verify Identity")
                    .setSubtitle("Confirm fingerprint or lock to enable Wang App Lock")
                    .setDeviceCredentialAllowed(true)
                    .build();
        }

        BiometricPrompt biometricPrompt = new BiometricPrompt(
                this,
                ContextCompat.getMainExecutor(this),
                new BiometricPrompt.AuthenticationCallback() {
                    @Override
                    public void onAuthenticationSucceeded(@NonNull BiometricPrompt.AuthenticationResult result) {
                        super.onAuthenticationSucceeded(result);
                        getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                                .edit()
                                .putBoolean(KEY_BIOMETRIC_ENABLED, true)
                                .apply();
                        performHaptic("success");
                        notifyWebBiometricState(true);
                        Toast.makeText(MainActivity.this, "Biometric App Lock enabled! 🔒", Toast.LENGTH_SHORT).show();
                    }

                    @Override
                    public void onAuthenticationError(int errorCode, @NonNull CharSequence errString) {
                        super.onAuthenticationError(errorCode, errString);
                        notifyWebBiometricState(false);
                    }
                }
        );

        try {
            biometricPrompt.authenticate(promptInfo);
        } catch (Exception e) {
            Toast.makeText(this, "Biometric authentication not configured on this device", Toast.LENGTH_LONG).show();
            notifyWebBiometricState(false);
        }
    }

    private void notifyWebBiometricState(boolean enabled) {
        if (mWebView != null) {
            String js = "if (window.wangOnBiometricStateChanged) { window.wangOnBiometricStateChanged(" + enabled + "); }";
            mWebView.evaluateJavascript(js, null);
        }
    }

    private void applyAndScheduleReminder(int hour, int minute) {
        try {
            getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit()
                    .putBoolean(DailyReminderReceiver.KEY_REMINDER_ENABLED, true)
                    .putInt(DailyReminderReceiver.KEY_REMINDER_HOUR, hour)
                    .putInt(DailyReminderReceiver.KEY_REMINDER_MINUTE, minute)
                    .apply();

            DailyReminderReceiver.createNotificationChannel(this);
            DailyReminderReceiver.scheduleReminder(this, hour, minute);

            notifyWebReminderState(true);
            String timeStr = String.format(Locale.getDefault(), "%02d:%02d", hour, minute);
            Toast.makeText(this, "Daily reminder scheduled for " + timeStr + " 🔔", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            Toast.makeText(this, "Unable to schedule reminder on this device", Toast.LENGTH_SHORT).show();
        }
    }

    private void notifyWebReminderState(boolean enabled) {
        if (mWebView != null) {
            String js = "if (window.wangOnReminderStateChanged) { window.wangOnReminderStateChanged(" + enabled + "); }";
            mWebView.evaluateJavascript(js, null);
        }
    }

    // ── Intent & Shortcut URL routing ──

    private String getUrlFromIntent(Intent intent) {
        String base = getString(R.string.app_web_url);
        if (!base.endsWith("/")) base += "/";

        if (intent != null) {
            String action = intent.getStringExtra("shortcut_action");
            if (action != null) {
                switch (action) {
                    case "new_expense":
                        return base + "?action=new_expense";
                    case "new_income":
                        return base + "?action=new_income";
                    case "graphs":
                        return base + "graphs/";
                    case "wallets":
                        return base + "wallets/";
                }
            }
            Uri data = intent.getData();
            if (data != null && data.toString().startsWith("http")) {
                return data.toString();
            }
        }
        return base;
    }

    private void handleShortcutIntent(Intent intent) {
        if (intent == null || mWebView == null) return;
        String action = intent.getStringExtra("shortcut_action");
        String base = getString(R.string.app_web_url);
        if (!base.endsWith("/")) base += "/";

        if ("new_expense".equals(action)) {
            mWebView.loadUrl(base + "?action=new_expense");
        } else if ("new_income".equals(action)) {
            mWebView.loadUrl(base + "?action=new_income");
        } else if ("graphs".equals(action)) {
            mWebView.loadUrl(base + "graphs/");
        } else if ("wallets".equals(action)) {
            mWebView.loadUrl(base + "wallets/");
        } else if (intent.getData() != null && intent.getData().toString().startsWith("http")) {
            mWebView.loadUrl(intent.getData().toString());
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleShortcutIntent(intent);
    }

    private void syncSwipeRefreshState() {
        boolean isAtTop = mWebView.getScrollY() == 0 && !mWebView.canScrollVertically(-1);
        boolean canRefresh = mPageAllowsRefresh && !mIsScrollableActive && isAtTop;
        mSwipeRefresh.setEnabled(canRefresh);
    }

    private boolean isPullToRefreshAllowedForUrl(String url) {
        if (url == null) return true;
        try {
            Uri uri = Uri.parse(url);
            String path = uri.getPath();
            if (path == null) return true;
            if (path.contains("/new") || path.contains("/edit") || path.contains("/delete")
                    || path.contains("/login") || path.contains("/signup")) {
                return false;
            }
        } catch (Exception ignored) {}
        return true;
    }

    private void setupWebView() {
        WebSettings webSettings = mWebView.getSettings();

        // Core web engine settings
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setDatabaseEnabled(true);
        webSettings.setAllowFileAccess(true);
        webSettings.setAllowContentAccess(true);

        // Hardware acceleration and gesture-free audio
        webSettings.setMediaPlaybackRequiresUserGesture(false);

        // Cache & responsive viewport
        webSettings.setCacheMode(WebSettings.LOAD_DEFAULT);
        webSettings.setUseWideViewPort(true);
        webSettings.setLoadWithOverviewMode(true);
        webSettings.setSupportZoom(false);
        webSettings.setBuiltInZoomControls(false);
        webSettings.setDisplayZoomControls(false);

        // Identify as Wang Native Android wrapper in User-Agent header
        String customUA = webSettings.getUserAgentString() + " WangNativeAndroid/1.1.0";
        webSettings.setUserAgentString(customUA);

        // Persistent Cookies & Session management
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(mWebView, true);

        // Fast scroll physics
        mWebView.setOverScrollMode(View.OVER_SCROLL_NEVER);

        // Register AndroidBridge JavaScript interface
        mWebView.addJavascriptInterface(new WebAppInterface(), "AndroidBridge");

        // DownloadListener for CSV Exports
        mWebView.setDownloadListener((url, userAgent, contentDisposition, mimetype, contentLength) -> {
            handleDownload(url, userAgent, contentDisposition, mimetype);
        });

        // Set WebViewClient
        mWebView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme();

                if (scheme == null) return false;

                if (scheme.equalsIgnoreCase("tel") ||
                    scheme.equalsIgnoreCase("mailto") ||
                    scheme.equalsIgnoreCase("sms") ||
                    scheme.equalsIgnoreCase("whatsapp") ||
                    scheme.equalsIgnoreCase("intent")) {
                    try {
                        Intent intent = new Intent(Intent.ACTION_VIEW, uri);
                        startActivity(intent);
                        return true;
                    } catch (ActivityNotFoundException e) {
                        return true;
                    }
                }

                return false;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                super.onPageStarted(view, url, favicon);
                mPageAllowsRefresh = isPullToRefreshAllowedForUrl(url);
                syncSwipeRefreshState();
            }

            @Override
            public void doUpdateVisitedHistory(WebView view, String url, boolean isReload) {
                super.doUpdateVisitedHistory(view, url, isReload);
                mPageAllowsRefresh = isPullToRefreshAllowedForUrl(url);
                syncSwipeRefreshState();
                injectSafeAreaInsets(mLastTopInsetsDp, mLastBottomInsetsDp);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                mSwipeRefresh.setRefreshing(false);
                CookieManager.getInstance().flush();
                mPageAllowsRefresh = isPullToRefreshAllowedForUrl(url);
                syncSwipeRefreshState();
                injectScrollHandler(view);
                injectSafeAreaInsets(mLastTopInsetsDp, mLastBottomInsetsDp);
                view.evaluateJavascript("document.documentElement.getAttribute('data-theme')", val -> {
                    if (val != null) {
                        updateSystemBarIcons(val.contains("dark"));
                    }
                });
                if (mPendingCapturedPhotoBase64 != null) {
                    view.postDelayed(() -> deliverPendingPhotoToWebView(), 400);
                }
            }

            @Override
            public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                if (mWebView != null) {
                    ViewGroup parent = (ViewGroup) mWebView.getParent();
                    if (parent != null) {
                        parent.removeView(mWebView);
                    }
                    mWebView.destroy();
                    mWebView = null;
                }
                recreate();
                return true;
            }
        });

        // Set WebChromeClient for Receipt File Chooser
        mWebView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                super.onProgressChanged(view, newProgress);
                if (newProgress >= 100) {
                    mSwipeRefresh.setRefreshing(false);
                }
            }

            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback,
                                              FileChooserParams fileChooserParams) {
                if (mFilePathCallback != null) {
                    mFilePathCallback.onReceiveValue(null);
                    mFilePathCallback = null;
                }
                mFilePathCallback = filePathCallback;

                Intent takePictureIntent = null;
                File photoFile = null;
                try {
                    photoFile = createImageFile();
                    mCameraPhotoPath = photoFile.getAbsolutePath();
                    Uri photoURI = FileProvider.getUriForFile(MainActivity.this,
                            getApplicationContext().getPackageName() + ".fileprovider",
                            photoFile);
                    mCameraPhotoUri = photoURI;

                    takePictureIntent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                    takePictureIntent.putExtra(MediaStore.EXTRA_OUTPUT, photoURI);
                    takePictureIntent.setClipData(ClipData.newRawUri("Receipt Photo", photoURI));
                    takePictureIntent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                } catch (Exception ex) {
                    mCameraPhotoPath = null;
                    mCameraPhotoUri = null;
                }

                Intent contentSelectionIntent = fileChooserParams.createIntent();
                contentSelectionIntent.setType("image/*");

                Intent[] intentArray;
                if (takePictureIntent != null) {
                    intentArray = new Intent[]{takePictureIntent};
                } else {
                    intentArray = new Intent[0];
                }

                Intent chooserIntent = new Intent(Intent.ACTION_CHOOSER);
                chooserIntent.putExtra(Intent.EXTRA_INTENT, contentSelectionIntent);
                chooserIntent.putExtra(Intent.EXTRA_TITLE, "Select Receipt Photo");
                chooserIntent.putExtra(Intent.EXTRA_INITIAL_INTENTS, intentArray);

                try {
                    mFileChooserLauncher.launch(chooserIntent);
                } catch (ActivityNotFoundException e) {
                    mFilePathCallback = null;
                    Toast.makeText(MainActivity.this, "Cannot open photo chooser", Toast.LENGTH_SHORT).show();
                    return false;
                }

                return true;
            }
        });
    }

    private void handleDownload(String url, String userAgent, String contentDisposition, String mimeType) {
        try {
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            if (mimeType != null && !mimeType.isEmpty()) {
                request.setMimeType(mimeType);
            }
            String cookies = CookieManager.getInstance().getCookie(url);
            if (cookies != null && !cookies.isEmpty()) {
                request.addRequestHeader("cookie", cookies);
            }
            if (userAgent != null && !userAgent.isEmpty()) {
                request.addRequestHeader("User-Agent", userAgent);
            }
            request.setDescription("Downloading Wang transactions data...");
            String filename = URLUtil.guessFileName(url, contentDisposition, mimeType);
            if (filename == null || filename.isEmpty() || filename.endsWith(".bin")) {
                filename = "wang_transactions.csv";
            }
            request.setTitle(filename);
            request.allowScanningByMediaScanner();
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename);

            DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            if (dm != null) {
                dm.enqueue(request);
                Toast.makeText(getApplicationContext(), "Downloading " + filename + " to Downloads...", Toast.LENGTH_SHORT).show();
            }
        } catch (Exception e) {
            try {
                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                startActivity(intent);
            } catch (Exception ex) {
                Toast.makeText(getApplicationContext(), "Unable to download file", Toast.LENGTH_SHORT).show();
            }
        }
    }

    private void injectScrollHandler(WebView view) {
        String script = "(function() {" +
                "  if (window.__wangTouchBridgeInstalled) return;" +
                "  window.__wangTouchBridgeInstalled = true;" +
                "  function isScrollable(el) {" +
                "    if (!el || el === document.body || el === document.documentElement) return false;" +
                "    if (el.classList && (" +
                "      el.classList.contains('sheet-scroll') ||" +
                "      el.classList.contains('cat-grid') ||" +
                "      el.classList.contains('cat-cell') ||" +
                "      el.classList.contains('picker-list') ||" +
                "      el.classList.contains('picker-icon-grid') ||" +
                "      el.classList.contains('filter-sheet-body') ||" +
                "      el.classList.contains('filter-cats-wrap') ||" +
                "      el.classList.contains('sheet')" +
                "    )) return true;" +
                "    try {" +
                "      var s = window.getComputedStyle(el);" +
                "      var oy = s.overflowY; var ox = s.overflowX;" +
                "      return ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 2) ||" +
                "             ((ox === 'auto' || ox === 'scroll') && el.scrollWidth > el.clientWidth + 2);" +
                "    } catch(e) { return false; }" +
                "  }" +
                "  function findScrollable(target) {" +
                "    var el = target;" +
                "    while (el && el !== document.body && el !== document.documentElement) {" +
                "      if (isScrollable(el)) return el;" +
                "      el = el.parentElement;" +
                "    }" +
                "    return null;" +
                "  }" +
                "  function hasActiveSheetOrOverlay() {" +
                "    var openSheet = document.querySelector('.sheet.open, .detail-sheet.open, .budget-sheet.open, .filter-sheet.open, .confirm-sheet.open, .picker.open, .date-sheet.open, .month-popover.open, .modal-open, #lightbox.active');" +
                "    if (openSheet) return true;" +
                "    var overlay = document.querySelector('.sheet-overlay.show, .detail-overlay.show, .picker-overlay.show, .date-overlay.show, .filter-overlay.show, .confirm-overlay.show, .budget-overlay.show');" +
                "    if (overlay) return true;" +
                "    var a = document.activeElement;" +
                "    if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT')) return true;" +
                "    return false;" +
                "  }" +
                "  function syncState(touchTarget) {" +
                "    if (!window.AndroidBridge) return;" +
                "    var path = window.location.pathname;" +
                "    var isForm = path.includes('/new') || path.includes('/edit') || path.includes('/delete') ||" +
                "                 path.includes('/login') || path.includes('/signup');" +
                "    if (isForm) {" +
                "      window.AndroidBridge.setPullToRefreshEnabled(false);" +
                "      window.AndroidBridge.setScrollableActive(true);" +
                "      return;" +
                "    }" +
                "    var isScroll = touchTarget ? !!findScrollable(touchTarget) : false;" +
                "    var overlay = hasActiveSheetOrOverlay();" +
                "    window.AndroidBridge.setScrollableActive(isScroll || overlay);" +
                "  }" +
                "  document.addEventListener('touchstart', function(e) { syncState(e.target); }, { passive: true, capture: true });" +
                "  document.addEventListener('touchmove', function(e) {" +
                "    if (findScrollable(e.target) && window.AndroidBridge) window.AndroidBridge.setScrollableActive(true);" +
                "  }, { passive: true, capture: true });" +
                "  document.addEventListener('touchend', function(e) {" +
                "    setTimeout(function() { syncState(null); }, 60);" +
                "  }, { passive: true, capture: true });" +
                "  document.addEventListener('touchcancel', function(e) {" +
                "    setTimeout(function() { syncState(null); }, 60);" +
                "  }, { passive: true, capture: true });" +
                "  document.addEventListener('focusin', function(e) {" +
                "    if (window.AndroidBridge) window.AndroidBridge.setScrollableActive(true);" +
                "  }, { capture: true });" +
                "  document.addEventListener('focusout', function(e) {" +
                "    setTimeout(function() { syncState(null); }, 150);" +
                "  }, { capture: true });" +
                "  window.addEventListener('popstate', function() { syncState(null); });" +
                "  document.addEventListener('turbo:load', function() { syncState(null); });" +
                "  document.addEventListener('turbo:render', function() { syncState(null); });" +
                "  syncState(null);" +
                "})();";
        view.evaluateJavascript(script, null);
    }

    private File createImageFile() throws IOException {
        String timeStamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(new Date());
        String imageFileName = "JPEG_" + timeStamp + "_";
        File storageDir = getExternalFilesDir(Environment.DIRECTORY_PICTURES);
        if (storageDir == null || !storageDir.exists()) {
            storageDir = getCacheDir();
        }
        return File.createTempFile(
                imageFileName,
                ".jpg",
                storageDir
        );
    }

    private void setupFileChooserLauncher() {
        mFileChooserLauncher = registerForActivityResult(
                new ActivityResultContracts.StartActivityForResult(),
                new ActivityResultCallback<ActivityResult>() {
                    @Override
                    public void onActivityResult(ActivityResult result) {
                        Uri[] results = null;

                        if (result.getResultCode() == RESULT_OK) {
                            Intent intent = result.getData();
                            boolean isCamera = false;
                            if (mCameraPhotoPath != null) {
                                File file = new File(mCameraPhotoPath);
                                if (file.exists() && file.length() > 0) {
                                    isCamera = true;
                                }
                            }

                            if (isCamera && (intent == null || (intent.getData() == null && intent.getClipData() == null))) {
                                if (mCameraPhotoUri != null) {
                                    results = new Uri[]{mCameraPhotoUri};
                                } else if (mCameraPhotoPath != null) {
                                    try {
                                        Uri uri = FileProvider.getUriForFile(MainActivity.this,
                                                getApplicationContext().getPackageName() + ".fileprovider",
                                                new File(mCameraPhotoPath));
                                        results = new Uri[]{uri};
                                    } catch (Exception e) {
                                        results = new Uri[]{Uri.fromFile(new File(mCameraPhotoPath))};
                                    }
                                }

                                if (mFilePathCallback == null && mCameraPhotoPath != null) {
                                    mPendingCapturedPhotoBase64 = readImageAsBase64DataUrl(mCameraPhotoPath);
                                    deliverPendingPhotoToWebView();
                                }
                            } else if (intent != null) {
                                if (intent.getClipData() != null) {
                                    int count = intent.getClipData().getItemCount();
                                    results = new Uri[count];
                                    for (int i = 0; i < count; i++) {
                                        results[i] = intent.getClipData().getItemAt(i).getUri();
                                    }
                                } else if (intent.getData() != null) {
                                    results = new Uri[]{intent.getData()};
                                } else if (isCamera && mCameraPhotoUri != null) {
                                    results = new Uri[]{mCameraPhotoUri};
                                }
                            } else if (isCamera && mCameraPhotoUri != null) {
                                results = new Uri[]{mCameraPhotoUri};
                                if (mFilePathCallback == null && mCameraPhotoPath != null) {
                                    mPendingCapturedPhotoBase64 = readImageAsBase64DataUrl(mCameraPhotoPath);
                                    deliverPendingPhotoToWebView();
                                }
                            }
                        }

                        if (results == null && mCameraPhotoPath != null) {
                            try {
                                File file = new File(mCameraPhotoPath);
                                if (file.exists() && file.length() == 0) {
                                    file.delete();
                                }
                            } catch (Exception ignored) {}
                        }

                        if (mFilePathCallback != null) {
                            mFilePathCallback.onReceiveValue(results);
                            mFilePathCallback = null;
                        }
                    }
                }
        );
    }

    private String readImageAsBase64DataUrl(String filePath) {
        try {
            File file = new File(filePath);
            if (!file.exists() || file.length() == 0) return null;

            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inJustDecodeBounds = true;
            BitmapFactory.decodeFile(filePath, options);

            int maxDim = 1280;
            int inSampleSize = 1;
            int width = options.outWidth;
            int height = options.outHeight;
            while ((width / inSampleSize) > maxDim || (height / inSampleSize) > maxDim) {
                inSampleSize *= 2;
            }

            options.inJustDecodeBounds = false;
            options.inSampleSize = inSampleSize;
            Bitmap bitmap = BitmapFactory.decodeFile(filePath, options);
            if (bitmap == null) return null;

            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            bitmap.compress(Bitmap.CompressFormat.JPEG, 85, baos);
            byte[] bytes = baos.toByteArray();
            bitmap.recycle();

            String base64 = Base64.encodeToString(bytes, Base64.NO_WRAP);
            return "data:image/jpeg;base64," + base64;
        } catch (Exception e) {
            return null;
        }
    }

    private void deliverPendingPhotoToWebView() {
        if (mWebView != null && mPendingCapturedPhotoBase64 != null) {
            String js = "if (window.wangAttachCapturedPhoto) { window.wangAttachCapturedPhoto('" + mPendingCapturedPhotoBase64 + "'); }";
            mWebView.evaluateJavascript(js, val -> {
                if (val != null && "true".equalsIgnoreCase(val.trim().replace("\"", ""))) {
                    mPendingCapturedPhotoBase64 = null;
                }
            });
        }
    }

    // ── Smart Back Navigation ──

    private void setupBackNavigation() {
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (mWebView != null) {
                    // Check if open web bottom sheet or modal can consume back gesture
                    mWebView.evaluateJavascript(
                            "(function() { return !!(window.wangHandleBackPressed && window.wangHandleBackPressed()); })()",
                            result -> {
                                boolean consumed = "true".equalsIgnoreCase(String.valueOf(result).trim().replace("\"", ""));
                                if (!consumed) {
                                    runOnUiThread(() -> {
                                        if (mWebView != null && mWebView.canGoBack()) {
                                            mWebView.goBack();
                                        } else {
                                            setEnabled(false);
                                            getOnBackPressedDispatcher().onBackPressed();
                                        }
                                    });
                                }
                            }
                    );
                    return;
                }
                setEnabled(false);
                getOnBackPressedDispatcher().onBackPressed();
            }
        });
    }

    @Override
    protected void onSaveInstanceState(@NonNull Bundle outState) {
        super.onSaveInstanceState(outState);
        if (mWebView != null) {
            mWebView.saveState(outState);
        }
        if (mCameraPhotoPath != null) {
            outState.putString("camera_photo_path", mCameraPhotoPath);
        }
        if (mCameraPhotoUri != null) {
            outState.putParcelable("camera_photo_uri", mCameraPhotoUri);
        }
        if (mPendingCapturedPhotoBase64 != null) {
            outState.putString("pending_photo_base64", mPendingCapturedPhotoBase64);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (mWebView != null) {
            mWebView.onPause();
        }
        mLastPausedTimestamp = System.currentTimeMillis();
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (mWebView != null) {
            mWebView.onResume();
            if (mWebView.getUrl() == null) {
                mWebView.loadUrl(getString(R.string.app_web_url));
            }
        }
        if (mSwipeRefresh != null) {
            mSwipeRefresh.setRefreshing(false);
        }
        CookieManager.getInstance().flush();

        // Biometric re-lock if past grace period
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        boolean biometricEnabled = prefs.getBoolean(KEY_BIOMETRIC_ENABLED, false);
        if (biometricEnabled && mLastPausedTimestamp > 0 &&
                (System.currentTimeMillis() - mLastPausedTimestamp) > LOCK_GRACE_PERIOD_MS) {
            lockAppWithBiometrics();
        }
    }

    @Override
    protected void onDestroy() {
        if (mWebView != null) {
            mWebView.destroy();
        }
        super.onDestroy();
    }
}
