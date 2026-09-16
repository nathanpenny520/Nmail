# Nmail GUI cask 模板（自家 tap 仓 nathanpenny520/homebrew-nmail 的 Casks/nmail.rb）。
# 发版时由 release.yml homebrew-tap job 渲染版本号与 SHA256 后 create-or-update；
# 模板结构改动走主仓；brew 下载不打 quarantine 属性 → 无 Gatekeeper 警告。
cask "nmail" do
  version "{{VERSION}}"
  sha256 "{{SHA256}}"

  url "https://github.com/nathanpenny520/Nmail/releases/download/v#{version}/nmail-macos-arm64.dmg"
  name "Nmail"
  desc "AI 驱动的本地聚合邮箱客户端"
  homepage "https://github.com/nathanpenny520/Nmail"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on mac: ">= :big_sur"
  depends_on arch: :arm64

  app "Nmail.app"
end
