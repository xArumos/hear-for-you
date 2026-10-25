import UIKit
import Capacitor
import AVFAudio

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    private var wasBackgrounded = false
    private var interruptionObserver: NSObjectProtocol?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard let windowScene = scene as? UIWindowScene else { return }

        window = UIWindow(windowScene: windowScene)
        window?.rootViewController = CAPBridgeViewController()
        window?.makeKeyAndVisible()
        interruptionObserver = NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification, object: nil, queue: .main
        ) { [weak self] notification in
            guard let kind = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                  kind == AVAudioSession.InterruptionType.began.rawValue else { return }
            self?.stopForegroundCapture()
        }

        SceneDelegateProxy.shared.scene(scene, willConnectTo: session, options: connectionOptions)
    }

    // Foreground-only release: do not treat permission dialogs as backgrounding.
    func sceneDidEnterBackground(_ scene: UIScene) {
        wasBackgrounded = true
        stopForegroundCapture()
    }

    func sceneWillEnterForeground(_ scene: UIScene) {
        if wasBackgrounded { stopForegroundCapture() }
        wasBackgrounded = false
        // Never resume microphone capture automatically.
    }

    private func stopForegroundCapture() {
        guard let controller = window?.rootViewController as? CAPBridgeViewController,
              let webView = controller.webView else { return }
        webView.evaluateJavaScript("window.dispatchEvent(new Event('hear-for-you-native-inactive'))", completionHandler: nil)
        webView.setAllMediaCaptureState(.none, completionHandler: nil)
    }

    func sceneDidDisconnect(_ scene: UIScene) {
        stopForegroundCapture()
        if let observer = interruptionObserver { NotificationCenter.default.removeObserver(observer) }
        interruptionObserver = nil
    }

    func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
        SceneDelegateProxy.shared.scene(scene, openURLContexts: URLContexts)
    }

    func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
        SceneDelegateProxy.shared.scene(scene, continue: userActivity)
    }
}
