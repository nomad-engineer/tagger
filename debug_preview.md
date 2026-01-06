I can see the issue now. The problem is that while we've made all the right changes, the preview is not being actively triggered to update. Let me check where `_update_preview()` should be called and add the missing calls.

The key issues:
1. `_update_preview()` is not being called after initialization
2. We need to trigger preview updates when the mode changes
3. The preview should update when mask changes occur

Let me add the missing preview update calls.