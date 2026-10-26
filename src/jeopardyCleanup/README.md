# after checking out the dotfiles
systemctl --user daemon-reload
systemctl --user enable --now jeopardy-cleanup.timer
sudo loginctl enable-linger mmtrent     # stored in /var/lib/systemd/linger, outside $HOME
