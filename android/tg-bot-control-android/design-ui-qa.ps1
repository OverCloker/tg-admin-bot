$qaAdb='C:/Users/Abbadon/Documents/Codex/_android-build-tools/android-sdk/platform-tools/adb.exe'
function Tree {
    $qaXml=& $qaAdb -s emulator-5554 exec-out uiautomator dump /dev/tty
    return [xml]($qaXml -replace 'UI hierchary dumped to: /dev/tty','')
}
function TapNode($node) {
    if(!$node){throw 'Target missing from UI tree'}
    $bounds=[regex]::Matches($node.bounds,'\d+') | ForEach-Object {[int]$_.Value}
    & $qaAdb -s emulator-5554 shell input tap ([int](($bounds[0]+$bounds[2])/2)) ([int](($bounds[1]+$bounds[3])/2))
}
function Summary($tree) {
    $tree.SelectNodes('//node[@text!=""]') | ForEach-Object {'{0}: {1}' -f $_.text,$_.bounds}
}
$qaTree=Tree
TapNode ($qaTree.SelectNodes('//node[@class="android.widget.Button"]') | Where-Object {$_.text -match '^Завтра'} | Select-Object -First 1)
Summary (Tree)
$qaTree=Tree
TapNode ($qaTree.SelectNodes('//node[@class="android.widget.Button"]') | Where-Object {$_.text -match '^Сегодня'} | Select-Object -First 1)
$qaTree=Tree
TapNode ($qaTree.SelectSingleNode('//node[@content-desc="Изменить населённый пункт и группу"]'))
$qaTree=Tree
TapNode ($qaTree.SelectSingleNode('//node[@class="android.widget.EditText"]'))
& $qaAdb -s emulator-5554 shell input keyevent KEYCODE_MOVE_END
& $qaAdb -s emulator-5554 shell input text '%s'
& $qaAdb -s emulator-5554 shell input keyevent 4
Summary (Tree)
Summary (Tree)
