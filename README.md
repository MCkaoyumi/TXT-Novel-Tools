# TXT小说工具箱
# python脚本
使用python将txt的电子小说转换为jpeg格式的图片
### 用途
在一些设备（如功能机）等上阅读txt电子小说时，可能出现没有对应的应用打开的情况，这个时候如果能够把txt转化为jpeg格式的图片，就能够实现阅读
### 特点
将章节分到了多个文件夹，保证了每个文件夹不多于指定数目的文件，这样跳转文件时便无需频繁按上下键
### 使用方法
#### 运行下载后的exe文件
打开即可，如有报毒请忽视
#### 运行python脚本
安装python 3，下载地址参见：<https://python.org/downloads>

运行以下命令安装必要的库
```
pip install Pillow
```
安装完成后双击打开程序，按照说明进行操作

程序代码的开头部分可以设置一些变量的默认配置
```
# 图片分辨率设置
default_width = 215
default_height = 290
# 文件夹层数设置
default_max_folders_per_level = 10 #最大文件夹层数
default_chapters_per_folder = 100
# 字体设置
default_font_size = 12
```
### 说明
本程序很大一部分是AI完成的，因为是作者自用，有很多不完善的地方是很正常的，发出来只是本着一个分享的态度，如有错误还请指出
# 打印小说的word模板
仓库中的`Novel Print.dotm`，或者是在release中的同名文件
### 注意
打印时请选择纵向翻转，双面打印，需要准备能够钉书籍中缝的订书机（会转头的）
