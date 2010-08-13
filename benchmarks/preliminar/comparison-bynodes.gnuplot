set terminal postscript colour enhanced landscape lw 1 10
set key box left top width 1 title 'Test run'
set xlabel 'Number of namespaces'
set ylabel 'Processing cost per packet (10E-6 sec)'
set title 'Comparison of the different methods @1000b packets'
set xrange [0:35]
plot \
 'resultados-mathieu.txt' index 0 every 8::1 using 2:3 title "posixuser-ns3kernel" with linespoints, \
 'resultados-mathieu.txt' index 1 every 8::1 using 2:3 title "ns3user-ns3kernel" with linespoints, \
 'resultados-mathieu.txt' index 2 every 8::1 using 2:3 title "posixuser-linuxkernel-small" with linespoints, \
 'resultados-mathieu.txt' index 3 every 13::11 using 1:($10/$3) title "netns" with linespoints, \
 'resultados-mathieu.txt' index 4 every 13::11 using 1:($10/$3) title "netns+bridging" with linespoints

